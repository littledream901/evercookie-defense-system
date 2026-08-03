<?php
/**
 * 网关 HTTP 客户端。
 *
 * 职责：把访客上下文组装成 `/v2/decide` 请求体，完成签名，通过
 * `wp_remote_post` 发送，并按 `fail_mode` 处理超时 / 网关错误。
 *
 * 路由说明
 * --------
 * 实施计划里写的是 `/v2/decisions`，但阶段 1/2 实际实现的路由是 `/v2/decide`。
 * 此处用 `/v2/decide` ——两者若有出入以实际运行的路由为准。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** 返回给调用方的结构化结果。 */
class Fangyu_Decision_Result {
	/** @var string pass / serve_alt / redirect / challenge / deny / not_found */
	public $mechanism = 'pass';
	/** @var string trusted / suspect / hostile */
	public $verdict = 'trusted';
	/** @var string|null 跳转 URL（mechanism=redirect 时）。 */
	public $target_url = null;
	/** @var int[]|null 备用 URL 池（保留，当前版本网关只回单值）。 */
	public $target_urls = null;
	/** @var string|null 页面资源名（mechanism=serve_alt 时，gateway 填充 page_content）。 */
	public $page_content = null;
	/** @var string|null challenge / page_resource 键 */
	public $target_kind = null;
	/** @var string|null captcha / js（mechanism=challenge 时）。 */
	public $challenge_kind = null;
	/** @var string|null 挑战凭据（mechanism=challenge 时网关签发）。 */
	public $challenge_token = null;
	/** @var int HTTP 状态码 */
	public $http_status = 200;
	/** @var bool 此结论是否源自 fail_mode 回退（而非真实网关决策）。 */
	public $is_fallback = false;
	/**
	 * 服务端会话 token（sst_<hex32>）。
	 * pass 时注入 __fy_server_ctx，SDK 二次请求时携带给网关做 hybrid 关联。
	 * fallback 时为 null（网关未参与决策，无需关联）。
	 *
	 * @var string|null
	 */
	public $server_token = null;
}

/**
 * 与 V2 网关通信。
 */
class Fangyu_Client {

	/** @var string 实际运行的决策路由（计划文档有笔误写成 /v2/decisions）。 */
	const DECIDE_PATH = '/v2/decide';

	/** @var int 超时秒数（wp_remote_post timeout 参数）。 */
	const TIMEOUT_SECONDS = 3;

	/**
	 * 向网关请求一次访客裁决。
	 *
	 * @param array $context 访客上下文，至少含：
	 *   - appId          (int)
	 *   - ingress        (string) 固定 'adapter'
	 *   - ip             (string)
	 *   - fingerprint    (string) 可为空串
	 *   - visitUrl       (string)
	 *   - userAgent      (string)
	 *   - repeatKey      (string)
	 *   - repeatValue    (string)
	 * @return Fangyu_Decision_Result
	 */
	public static function decide( array $context ) {
		$gateway_url = Fangyu_Config::gateway_url();
		$site_id     = Fangyu_Config::site_id();
		$app_secret  = Fangyu_Config::app_secret();
		$fail_mode   = Fangyu_Config::fail_mode();

		if ( ! $gateway_url || ! $site_id || ! $app_secret ) {
			return self::fallback( $fail_mode );
		}

		// 生成服务端会话 token（sst_<hex32>），传入 context.extra。
		// SDK 二次请求时携带此 token，网关在 hybrid_lookup 阶段将两层信号合并。
		$server_token           = self::generate_server_token();
		$context['extra']       = array( 'serverToken' => $server_token );

		$body   = array(
			'context'        => $context,
			'requireDetails' => false,
		);
		$signed = Fangyu_Signer::sign_body( $body, $app_secret );

		$url      = $gateway_url . self::DECIDE_PATH;
		$response = wp_remote_post(
			$url,
			array(
				'timeout'     => self::TIMEOUT_SECONDS,
				'headers'     => array(
					'Content-Type' => 'application/json; charset=utf-8',
					'X-App-Key'    => $site_id,
				),
				'body'        => wp_json_encode( $signed ),
				'data_format' => 'body',
			)
		);

		if ( is_wp_error( $response ) ) {
			// 连接失败、超时等。
			return self::fallback( $fail_mode );
		}

		$status = (int) wp_remote_retrieve_response_code( $response );
		if ( $status < 200 || $status >= 300 ) {
			// 4xx/5xx：网关返回可解析响应但请求有问题；fail-open 时放行，
			// fail-closed 时拦截。不区分 4xx vs 5xx，两者都超出客户端控制范围。
			return self::fallback( $fail_mode );
		}

		$raw  = wp_remote_retrieve_body( $response );
		$data = json_decode( $raw, true );
		if ( ! is_array( $data ) ) {
			return self::fallback( $fail_mode );
		}

		// 支持两种响应形状：
		//   { verdict, mechanism, ... }         — 裸响应
		//   { data: { verdict, mechanism, ... } } — 包装响应（与 SDK 一致）
		$payload = isset( $data['data'] ) && is_array( $data['data'] ) ? $data['data'] : $data;

		$result               = self::parse_response( $payload );
		$result->server_token = $server_token;
		return $result;
	}

	// ── 私有辅助 ────────────────────────────────────────────────────────────

	/**
	 * 把网关 JSON 响应映射到结构化对象。
	 *
	 * @param array $d 响应 payload。
	 * @return Fangyu_Decision_Result
	 */
	private static function parse_response( array $d ) {
		$r = new Fangyu_Decision_Result();

		$mechanism       = isset( $d['mechanism'] ) ? (string) $d['mechanism'] : 'pass';
		$allowed         = array( 'pass', 'serve_alt', 'redirect', 'challenge', 'deny', 'not_found' );
		$r->mechanism    = in_array( $mechanism, $allowed, true ) ? $mechanism : 'pass';
		$r->verdict      = isset( $d['verdict'] ) ? (string) $d['verdict'] : 'trusted';
		$r->target_url   = isset( $d['targetUrl'] ) ? (string) $d['targetUrl'] : null;
		$r->page_content = isset( $d['pageContent'] ) && is_string( $d['pageContent'] )
			? $d['pageContent'] : null;
		$r->target_kind  = isset( $d['targetKind'] ) ? (string) $d['targetKind'] : null;

		if ( isset( $d['challengeKind'] ) ) {
			$ck = (string) $d['challengeKind'];
			$r->challenge_kind = in_array( $ck, array( 'captcha', 'js' ), true ) ? $ck : null;
		}

		$r->challenge_token = isset( $d['challengeToken'] ) && is_string( $d['challengeToken'] )
			? $d['challengeToken'] : null;

		$r->http_status  = isset( $d['httpStatus'] ) ? (int) $d['httpStatus'] : 200;
		$r->is_fallback  = false;
		return $r;
	}

	/**
	 * 构造 fail_mode 回退决策。
	 *
	 * @param string $mode 'open' 或 'closed'。
	 * @return Fangyu_Decision_Result
	 */
	private static function fallback( $mode ) {
		$r = new Fangyu_Decision_Result();
		$r->is_fallback = true;
		if ( 'closed' === $mode ) {
			$r->mechanism  = 'deny';
			$r->verdict    = 'hostile';
			$r->http_status = 403;
		}
		// 'open' 保持默认 pass + trusted + 200。
		// server_token 不设置：网关未参与决策，无 hybrid 关联。
		return $r;
	}

	/**
	 * 生成服务端会话 token。
	 *
	 * 格式：sst_<32 位随机十六进制>。
	 * 使用 random_bytes（PHP 7+ 密码学安全随机数），
	 * 退回 openssl_random_pseudo_bytes，最终退回 mt_rand（不安全但不崩溃）。
	 *
	 * @return string
	 */
	private static function generate_server_token() {
		if ( function_exists( 'random_bytes' ) ) {
			$bytes = random_bytes( 16 );
		} elseif ( function_exists( 'openssl_random_pseudo_bytes' ) ) {
			$bytes = openssl_random_pseudo_bytes( 16 );
		} else {
			// 极端降级；mt_rand 不具密码学强度，但 token 本身不是机密，
			// 只是请求关联 ID，安全影响有限。
			$bytes = '';
			for ( $i = 0; $i < 16; $i++ ) {
				$bytes .= chr( mt_rand( 0, 255 ) );
			}
		}
		return 'sst_' . bin2hex( $bytes );
	}
}
