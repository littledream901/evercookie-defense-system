<?php
/**
 * 处置执行器：按网关 V2 `Mechanism` 执行相应动作。
 *
 * 与参考插件的对应关系
 * --------------------
 * 参考插件的 `JUMP_MODE`：
 *   0 → pass / serve_alt（原地渲染）
 *   1 → redirect（固定 URL 跳转）
 *   2 → redirect（多地址轮询）
 * V2 三层模型把上述压平成独立的 Mechanism 枚举；轮询由网关在选址时完成，
 * PHP 侧总是收到单个 `targetUrl`，不再自行取模。
 *
 * `serve_alt` 的 SDK 注入
 * ----------------------
 * 替代内容由网关的 `page_content` 字段填充；注入 SDK 后直接 `echo`，然后
 * `exit`，WP 模板引擎不再输出任何内容。等价于参考插件的 `loadHtmlWithScript`。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 处置执行。
 *
 * 所有方法假设调用时 WordPress headers 尚未发送（即在 `template_redirect`
 * 或更早的钩子里执行）。
 */
class Fangyu_Executor {

	/**
	 * 按 `Fangyu_Decision_Result` 执行处置。
	 *
	 * 返回 true 表示「请求已被处置完毕，WP 正常执行流应终止」；
	 * 返回 false 表示「放行，继续正常渲染」。
	 *
	 * @param Fangyu_Decision_Result $result 网关裁决。
	 * @return bool 是否已终止请求。
	 */
	public static function execute( Fangyu_Decision_Result $result ) {
		switch ( $result->mechanism ) {
			case 'pass':
				return false;

			case 'serve_alt':
				return self::do_serve_alt( $result );

			case 'redirect':
				return self::do_redirect( $result );

			case 'not_found':
				if ( 'status_only' === $result->target_kind ) {
					self::do_status_only( $result->http_status ?: 404 );
					return true;
				}
				self::do_not_found();
				return true;

			case 'deny':
				if ( 'status_only' === $result->target_kind ) {
					self::do_status_only( $result->http_status ?: 403 );
					return true;
				}
				self::do_deny( $result->http_status ?: 403 );
				return true;

			case 'challenge':
				self::do_challenge( $result );
				return true;

			default:
				// 未知机制：记 WARN 日志，按 fail_mode 决策。
				error_log( sprintf( '[fangyu] unknown mechanism: %s, fail_mode=%s', $result->mechanism, Fangyu_Config::fail_mode() ) );
				if ( 'closed' === Fangyu_Config::fail_mode() ) {
					self::do_deny( 403 );
					return true;
				}
				return false;
		}
	}

	// ── SDK 注入 ─────────────────────────────────────────────────────────────

	/**
	 * 在 wp_footer 钩子里注入 SDK + __fy_server_ctx。
	 *
	 * 第一层 pass 时调用。WP 正常渲染主题模板，SDK 在页面底部异步加载。
	 * server_token 非空时以 hybrid 模式运行（携带 token 做两层合并评分）；
	 * 为 null 时（fallback/standalone）SDK 独立完成全部决策。
	 *
	 * @param Fangyu_Decision_Result $result 第一层决策结果。
	 * @return void
	 */
	public static function schedule_sdk_injection( Fangyu_Decision_Result $result ) {
		// 把 result 传给闭包，避免全局变量
		add_action(
			'wp_footer',
			static function () use ( $result ) {
				echo self::sdk_injection_html( $result ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
			},
			99
		);
	}

	/**
	 * 构造完整注入 HTML（ctx 脚本 + SDK loader + onDecision handler）。
	 *
	 * @param Fangyu_Decision_Result $result
	 * @return string
	 */
	private static function sdk_injection_html( Fangyu_Decision_Result $result ) {
		$gateway_url   = Fangyu_Config::gateway_url();
		$site_id       = Fangyu_Config::site_id();
		$app_id        = Fangyu_Config::app_id();  // SDK 要求正整数，与 site_id 是两回事
		$server_token  = $result->server_token;    // null → standalone 模式
		$server_verdict = $result->verdict;
		$blocked_url   = '/blocked';
		$challenge_url = '/challenge';

		// 键名必须与 client-sdk 的 SdkConfig 对齐：apiBase / apiKey / appId。
		// 旧的 gatewayUrl / siteId 在 SDK 中不存在，validateConfig() 会直接抛错，
		// 导致第二层（浏览器指纹 + 决策）完全无法启动。
		$ctx = wp_json_encode(
			array_filter(
				array(
					'apiBase'       => $gateway_url,
					'apiKey'        => $site_id,
					'appId'         => $app_id,
					'serverVerdict' => $server_verdict,
					'serverToken'   => $server_token,   // null 时被 array_filter 剔除，JS 侧兜底
					'blockedUrl'    => $blocked_url,
					'challengeUrl'  => $challenge_url,
				),
				static function ( $v ) { return null !== $v; }
			),
			JSON_UNESCAPED_SLASHES
		);

		$sdk_src = esc_url( plugins_url( 'assets/sd-sdk.min.js', FANGYU_DEFENSE_FILE ) );

		// SDK 刻意保持 defer + DOMContentLoaded，**不要**改成同步阻塞。
		//
		// 两个原因：
		// 1. 本段由 schedule_sdk_injection() 挂在 wp_footer（优先级 99）输出，
		//    此时整个 body 已解析完毕。在这个位置改同步，时序上换不到任何东西，
		//    只会白白阻塞剩余解析。
		// 2. 更根本的是，本段只在**服务端已判 pass** 时才会被注入
		//    （见 fangyu-defense.php：execute() 返回 true 时直接 return，不注入）。
		//    能看到这段脚本的访客都已通过第一层，客户端层的跳转命中率按设计就低；
		//    且 HTML 此刻已完整下发，同步阻塞连「防正文泄露」都做不到。
		//    为少数残余命中让所有已放行的真人多等一次阻塞，不划算。
		//
		// 需要「HTML 都不下发」的拦截强度，靠的是第一层的服务端判定，不是这里。
		return <<<HTML
<script>window.__fy_server_ctx = {$ctx};</script>
<script src="{$sdk_src}" defer></script>
<script>
(function () {
  var ctx = window.__fy_server_ctx || {};

  // 这一段同步执行（不依赖 SDK）：缓存命中已知 hostile 时立刻跳，0ms 无网络。
  // 存 {v, exp} 而非裸 verdict，过期即视为未命中，使 ttlSeconds 真正生效。
  // 下面用 autoApply:false，SDK 自身的决策缓存不会自动生效，这一层必须保留。
  var _c = null;
  try { _c = JSON.parse(sessionStorage.getItem('_fy_v') || 'null'); } catch (e) {}
  if (_c && _c.exp > Date.now() && _c.v === 'hostile') {
    if (window.stop) { try { window.stop(); } catch (e) {} }
    location.replace(ctx.blockedUrl || '/blocked');
    return;
  }

  document.addEventListener('DOMContentLoaded', function () {
    // hybrid 模式：服务端已判 hostile 时 JS 兜底
    if (ctx.serverToken && ctx.serverVerdict === 'hostile') {
      try {
        sessionStorage.setItem('_fy_v', JSON.stringify({ v: 'hostile', exp: Date.now() + 300000 }));
      } catch (e) {}
      if (window.stop) { try { window.stop(); } catch (e) {} }
      location.replace(ctx.blockedUrl || '/blocked');
      return;
    }

    if (typeof SdSdk === 'undefined') return;
    if (!ctx.apiBase || !ctx.apiKey || !ctx.appId) return;

    // protect() 返回 Promise<{decision, applied}>。SDK 无 onDecision 配置项，
    // 处置回调必须从返回的 Promise 取，否则永远不会被调用。
    SdSdk.protect({
      apiBase:         ctx.apiBase,
      apiKey:          ctx.apiKey,
      appId:           ctx.appId,
      serverToken:     ctx.serverToken || '',   // hybrid / standalone 自动切换
      autoApply:       false,
      collectBehavior: true
    }).then(function (outcome) {
      var d = outcome && outcome.decision;
      if (!d) return;
      try {
        sessionStorage.setItem('_fy_v', JSON.stringify({
          v: d.verdict, exp: Date.now() + (d.ttlSeconds || 300) * 1000
        }));
      } catch (e) {}
      if (d.mechanism === 'redirect') {
        // 跳转前掐掉在途请求，省下已放行页面的剩余子资源流量
        if (window.stop) { try { window.stop(); } catch (e) {} }
        location.replace(d.targetUrl || ctx.blockedUrl);
      } else if (d.mechanism === 'challenge') {
        location.replace(ctx.challengeUrl + '?next=' + encodeURIComponent(location.href));
      } else if (d.mechanism === 'deny') {
        document.documentElement.innerHTML =
          '<body style="font:sans-serif;text-align:center;padding:80px"><h1>403</h1></body>';
      }
      // mechanism === 'pass' → 不做任何干预，页面正常渲染
    }).catch(function () { /* SDK 异常不影响页面 */ });
  });
}());
</script>
HTML;
	}

	// ── mechanism handlers ───────────────────────────────────────────────────

	/**
	 * serve_alt：输出替代页面并注入 SDK。
	 *
	 * 若 `page_content` 为空（网关未配置资源），降级为 deny(403)，
	 * 因为投放空内容等于给用户看一张空白页，体验比 403 更差。
	 *
	 * @param Fangyu_Decision_Result $r
	 * @return bool 始终 true（请求已终止）。
	 */
	private static function do_serve_alt( Fangyu_Decision_Result $r ) {
		$content = $r->page_content;
		if ( ! $content ) {
			self::do_deny( 403 );
			return true;
		}
		$inject = self::ctx_and_sdk_tag( $r );
		// 在 </body> 前注入 ctx + SDK，对应参考插件 loadHtmlWithScript 的正则。
		if ( false !== stripos( $content, '</body>' ) ) {
			$content = preg_replace( '/<\/body>/i', $inject . '</body>', $content, 1 );
		} else {
			$content .= $inject;
		}
		// 发 200，输出整替代文档。
		status_header( 200 );
		nocache_headers();
		echo $content; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		exit;
	}

	/**
	 * redirect：跳转（302）。
	 *
	 * 轮询地址选择由网关完成；`target_url` 已是单个确定地址。
	 * 无 URL 时降级为 deny(403)。
	 *
	 * @param Fangyu_Decision_Result $r
	 * @return bool 始终 true。
	 */
	private static function do_redirect( Fangyu_Decision_Result $r ) {
		$url = $r->target_url;
		if ( ! $url || ! self::is_safe_url( $url ) ) {
			self::do_deny( 403 );
			return true;
		}
		$status = ( $r->http_status >= 300 && $r->http_status < 400 ) ? $r->http_status : 302;
		wp_redirect( $url, $status );
		exit;
	}

	/**
	 * not_found：触发 WP 404 模板，保持自然的 404 外观，不泄露拦截信息。
	 *
	 * @return void
	 */
	private static function do_not_found() {
		global $wp_query;
		if ( $wp_query ) {
			$wp_query->set_404();
		}
		status_header( 404 );
		nocache_headers();
		// 加载当前主题的 404 模板。
		$template = get_query_template( '404' );
		if ( $template ) {
			include $template; // phpcs:ignore WordPressVIPMinimum.Files.IncludingFile.UsingVariable
			exit;
		}
		// 主题没有 404 模板的极端情况。
		wp_die( esc_html__( 'Page not found.', 'fangyu-defense' ), '', array( 'response' => 404 ) );
	}

	/**
	 * deny：返回 HTTP 状态码并终止。
	 *
	 * @param int $status HTTP 状态码，通常 403。
	 * @return void
	 */
	private static function do_deny( $status = 403 ) {
		nocache_headers();
		status_header( $status );
		wp_die(
			esc_html__( 'Access denied.', 'fangyu-defense' ),
			esc_html( (string) $status ),
			array( 'response' => $status )
		);
	}

	/**
	 * status_only：只回状态码，响应体为空。
	 *
	 * 与 do_deny / do_not_found 的区别是不输出任何页面内容——用于爬虫探测场景，
	 * 空响应体不给对方任何可用于指纹识别的错误页特征。
	 *
	 * @param int $status HTTP 状态码。
	 * @return void
	 */
	private static function do_status_only( $status ) {
		nocache_headers();
		status_header( $status );
		exit;
	}

	/**
	 * challenge：向访客展示挑战页。
	 *
	 * CAPTCHA 挑战：输出内嵌页面，由 SDK `challenge` 机制接管。
	 * JS 挑战：输出只含 SDK 的极简页面，SDK 执行 JS 检测后重定向回来。
	 *
	 * @param Fangyu_Decision_Result $r
	 * @return void
	 */
	private static function do_challenge( Fangyu_Decision_Result $r ) {
		nocache_headers();
		status_header( 403 );
		$return_url = esc_url( Fangyu_Visitor::get_page_url() );
		$inject     = self::ctx_and_sdk_tag( $r );
		$kind       = $r->challenge_kind ?: 'js';
		$content    = self::challenge_html( $kind, $return_url, $inject, $r );
		echo $content; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
		exit;
	}

	// ── helpers ──────────────────────────────────────────────────────────────

	/**
	 * 生成 ctx 脚本 + SDK `<script>` 标签。
	 *
	 * challenge / serve_alt 的自定义 HTML 通过此方法注入服务端上下文，
	 * 使 SDK 能以 hybrid 模式运行（server_token 非空时）。
	 *
	 * @param Fangyu_Decision_Result $result
	 * @return string
	 */
	private static function ctx_and_sdk_tag( Fangyu_Decision_Result $result ) {
		// 键名与 sdk_injection_html() 保持一致，对齐 SdkConfig。
		$ctx = wp_json_encode(
			array_filter(
				array(
					'apiBase'       => Fangyu_Config::gateway_url(),
					'apiKey'        => Fangyu_Config::site_id(),
					'appId'         => Fangyu_Config::app_id(),
					'serverVerdict' => $result->verdict,
					'serverToken'   => $result->server_token,
					'blockedUrl'    => '/blocked',
					'challengeUrl'  => '/challenge',
				),
				static function ( $v ) { return null !== $v; }
			),
			JSON_UNESCAPED_SLASHES
		);
		$sdk_src = esc_url( plugins_url( 'assets/sd-sdk.min.js', FANGYU_DEFENSE_FILE ) );
		return '<script>window.__fy_server_ctx = ' . $ctx . ';</script>'
			. '<script src="' . $sdk_src . '" defer></script>';
	}

	/**
	 * 生成 SDK `<script>` 标签（无 ctx，仅用于旧接口兼容）。
	 *
	 * @return string HTML script 标签。
	 */
	private static function sdk_script_tag() {
		$src = plugins_url( 'assets/sd-sdk.min.js', FANGYU_DEFENSE_FILE );
		return '<script src="' . esc_url( $src ) . '" defer></script>';
	}

	/**
	 * 挑战页 HTML。
	 *
	 * @param string                 $kind       captcha / js。
	 * @param string                 $return_url 挑战通过后跳回的页面。
	 * @param string                 $sdk_tag    SDK script 标签。
	 * @param Fangyu_Decision_Result $result     网关决策结果（携带 challenge_token）。
	 * @return string HTML 文档。
	 */
	private static function challenge_html( $kind, $return_url, $sdk_tag, Fangyu_Decision_Result $result ) {
		$title = esc_html__( 'Security Check', 'fangyu-defense' );
		$desc  = 'captcha' === $kind
			? esc_html__( 'Please complete the security check to continue.', 'fangyu-defense' )
			: esc_html__( 'Please wait while we verify your browser.', 'fangyu-defense' );
		// 挂载点携带的属性由 SDK 在加载后读取，用于自动认领并渲染真实挑战交互
		// （FY-DISP-004）：data-token 是网关签发的 HMAC 凭据，data-app-id /
		// data-api-key / data-gateway 是 SDK 提交答案到 /v2/challenge/verify
		// 所需的鉴权上下文。
		// data-fingerprint 必须与 decide 请求所用值一致——网关签发 token 时把它
		// 写进了载荷，校验端点会比对，不一致直接判失败。
		$token       = esc_attr( (string) $result->challenge_token );
		$app_id      = esc_attr( (string) Fangyu_Config::app_id() );
		$api_key     = esc_attr( Fangyu_Config::site_id() );
		$gateway_url = esc_attr( Fangyu_Config::gateway_url() );
		$fingerprint = esc_attr( Fangyu_Visitor::get_repeat_value() );
		return <<<HTML
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{$title}</title>
<style>
body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;
     min-height:100vh;margin:0;background:#f8f9fa}
.box{max-width:420px;padding:2rem;text-align:center;background:#fff;
     border-radius:8px;box-shadow:0 2px 16px rgba(0,0,0,.08)}
h1{font-size:1.2rem;margin:0 0 .5rem}p{color:#555;margin:0}
</style>
</head>
<body>
<div class="box">
  <h1>{$title}</h1>
  <p>{$desc}</p>
  <div id="fangyu-challenge" data-kind="{$kind}" data-return="{$return_url}"
       data-token="{$token}" data-app-id="{$app_id}" data-api-key="{$api_key}"
       data-gateway="{$gateway_url}" data-fingerprint="{$fingerprint}"></div>
</div>
{$sdk_tag}
</body>
</html>
HTML;
	}

	/**
	 * 安全 URL 校验：只允许 http / https 协议，防止 `javascript:` / `data:` XSS。
	 *
	 * @param string $url
	 * @return bool
	 */
	private static function is_safe_url( $url ) {
		$parsed = wp_parse_url( $url );
		if ( ! $parsed ) {
			return false;
		}
		$scheme = isset( $parsed['scheme'] ) ? strtolower( $parsed['scheme'] ) : '';
		return in_array( $scheme, array( 'http', 'https' ), true );
	}
}
