<?php
/**
 * 访客信息提取。
 *
 * 与参考插件的关系
 * ----------------
 * IP 提取逻辑从 `fangyu-php-full/core/fangyu_core.php::getClientIp` 移植：
 *   - 只信任 `CF-Connecting-IP` / `True-Client-IP` / `X-Real-IP`，
 *     **刻意忽略 `X-Forwarded-For`** 防伪造（参考插件的决定，此处继承）。
 *   - Peer 必须在可信代理 CIDR 段内才读转发头，否则直接取 `REMOTE_ADDR`。
 *   - 取首个 IP 并校验格式；不合法时兜底 `0.0.0.0`。
 *
 * repeat_key / repeat_value 与参考插件保持相同默认值（`_sd_0000`）以兼容
 * 已部署的 evercookie，改成 V2 后 SDK 写的 cookie 键不变。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 访客上下文：IP、repeat token、当前 URL、Referer。
 */
class Fangyu_Visitor {

	/** @var string evercookie 默认键名（对应 SDK DEFAULT_REPEAT_KEY）。 */
	const DEFAULT_REPEAT_KEY = '_sd_0000';

	/**
	 * 可信代理 CIDR 列表。
	 *
	 * 包含 Cloudflare 和 CloudFront IPv4/IPv6 段，与参考插件同步。
	 * 只有 `REMOTE_ADDR` 在这些段内时才相信 CF-Connecting-IP 等转发头。
	 *
	 * @var string[]
	 */
	private static $trusted_proxy_cidrs = array(
		// Cloudflare IPv4
		'103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22',
		'104.16.0.0/13', '104.24.0.0/14', '108.162.192.0/18',
		'131.0.72.0/22', '141.101.64.0/18', '162.158.0.0/15',
		'172.64.0.0/13', '173.245.48.0/20', '188.114.96.0/20',
		'190.93.240.0/20', '197.234.240.0/22', '198.41.128.0/17',
		// Cloudflare IPv6
		'2400:cb00::/32', '2405:8100::/32', '2405:b500::/32',
		'2606:4700::/32', '2803:f800::/32', '2c0f:f248::/32',
		'2a06:98c0::/29',
		// CloudFront
		'120.52.22.96/27', '205.251.249.0/24', '180.163.57.128/26',
		'204.246.168.0/22', '111.13.171.128/26', '18.160.0.0/15',
		'205.251.252.0/23', '54.192.0.0/16', '204.246.173.0/24',
		'54.230.200.0/21', '120.253.240.192/26', '116.129.226.128/26',
		'130.176.0.0/17', '108.156.0.0/14', '99.86.0.0/16',
	);

	/**
	 * 提取访客真实 IP。
	 *
	 * 为什么忽略 X-Forwarded-For
	 * --------------------------
	 * `XFF` 是客户端可自由伪造的头，追加模式又允许整个 hop 链条都参与写入，
	 * 恶意客户端只需在请求里加一个 `X-Forwarded-For: 1.2.3.4` 就能让真实 IP
	 * 被推后一位，选头时拿到的是伪造的 `1.2.3.4`。
	 * Cloudflare 的 `CF-Connecting-IP` 由 CF 边缘节点独立写入，客户端无法伪造，
	 * 语义明确且可信（前提：必须验证 peer 在 CF 的 CIDR 范围内）。
	 *
	 * @return string 规范化的 IP 地址，失败时返回 '0.0.0.0'。
	 */
	public static function get_client_ip() {
		$peer = isset( $_SERVER['REMOTE_ADDR'] ) ? trim( $_SERVER['REMOTE_ADDR'] ) : '';

		$candidate = null;
		if ( self::ip_in_trusted_proxy( $peer ) ) {
			// 只在可信代理后面读转发头。
			$headers = array( 'CF-Connecting-IP', 'True-Client-IP', 'X-Real-IP' );
			foreach ( $headers as $header ) {
				$server_key = 'HTTP_' . strtoupper( str_replace( '-', '_', $header ) );
				if ( ! empty( $_SERVER[ $server_key ] ) ) {
					// 转发头可能包含逗号分隔的多个 IP，取第一个。
					$candidate = trim( explode( ',', $_SERVER[ $server_key ] )[0] );
					break;
				}
			}
		}

		$ip = $candidate ?: $peer;
		if ( $ip && self::is_valid_ip( $ip ) ) {
			return $ip;
		}
		return '0.0.0.0';
	}

	/**
	 * 读取 evercookie repeat 值（指纹 ID）。
	 *
	 * 优先读 `$_GET`，其次读 `$_COOKIE`，与参考插件行为一致。
	 *
	 * @param string $key Cookie / query param 键名，默认 `_sd_0000`。
	 * @return string 读到的值，未找到返回空串。
	 */
	public static function get_repeat_value( $key = self::DEFAULT_REPEAT_KEY ) {
		if ( ! empty( $_GET[ $key ] ) ) {
			return sanitize_text_field( wp_unslash( $_GET[ $key ] ) );
		}
		if ( ! empty( $_COOKIE[ $key ] ) ) {
			return sanitize_text_field( wp_unslash( $_COOKIE[ $key ] ) );
		}
		return '';
	}

	/**
	 * 当前页面 URL（协议 + host + path + query），不含 fragment。
	 *
	 * 同参考插件的 `getPageUrl`：用 `home_url()` 而不是
	 * `$_SERVER['SERVER_NAME']` 以兼容反向代理后面的非标准 host 头。
	 *
	 * @return string
	 */
	public static function get_page_url() {
		// WP 自带的 wp_get_current_url / home_url 都合适，这里
		// 直接拼以避免 WP 全局函数不可用（如 early-hook 场景）。
		$scheme = is_ssl() ? 'https' : 'http';
		$host   = isset( $_SERVER['HTTP_HOST'] ) ? sanitize_text_field( wp_unslash( $_SERVER['HTTP_HOST'] ) ) : '';
		$uri    = isset( $_SERVER['REQUEST_URI'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REQUEST_URI'] ) ) : '/';
		return $scheme . '://' . $host . $uri;
	}

	/**
	 * Referer，当 referer 包含本站域名时返回空串（内部跳转不计入 referer）。
	 *
	 * 对应参考插件的 `getReferer` 行为。
	 *
	 * @return string 外部 referer 或空串。
	 */
	public static function get_referer() {
		$ref = isset( $_SERVER['HTTP_REFERER'] ) ? (string) $_SERVER['HTTP_REFERER'] : '';
		if ( ! $ref ) {
			return '';
		}
		$host = isset( $_SERVER['HTTP_HOST'] ) ? (string) $_SERVER['HTTP_HOST'] : '';
		if ( $host && false !== strpos( $ref, $host ) ) {
			return '';
		}
		return $ref;
	}

	/**
	 * 判断 IP 是否在给定 CIDR 段内（IPv4 与 IPv6 均支持）。
	 *
	 * @param string $ip   待检查 IP。
	 * @param string $cidr CIDR 表示法，如 `192.168.0.0/16`。
	 * @return bool
	 */
	public static function ip_in_range( $ip, $cidr ) {
		list( $subnet, $bits ) = array_pad( explode( '/', $cidr, 2 ), 2, null );
		if ( false === filter_var( $ip, FILTER_VALIDATE_IP )
			|| false === filter_var( $subnet, FILTER_VALIDATE_IP ) ) {
			return false;
		}
		$bits = (int) $bits;

		// IPv6
		if ( strpos( $ip, ':' ) !== false ) {
			if ( strpos( $subnet, ':' ) === false ) {
				return false; // IP 是 v6，subnet 是 v4
			}
			$ip_bin     = inet_pton( $ip );
			$subnet_bin = inet_pton( $subnet );
			if ( false === $ip_bin || false === $subnet_bin ) {
				return false;
			}
			$mask = str_repeat( "\xff", $bits >> 3 );
			if ( $bits % 8 ) {
				$mask .= chr( 0xff & ( 0xff << ( 8 - ( $bits % 8 ) ) ) );
			}
			$mask = str_pad( $mask, 16, "\x00" );
			return ( $ip_bin & $mask ) === ( $subnet_bin & $mask );
		}

		// IPv4
		if ( $bits < 0 || $bits > 32 ) {
			return false;
		}
		$mask      = $bits ? ( ~0 << ( 32 - $bits ) ) & 0xffffffff : 0;
		$ip_long   = ip2long( $ip );
		$sub_long  = ip2long( $subnet );
		if ( false === $ip_long || false === $sub_long ) {
			return false;
		}
		return ( $ip_long & $mask ) === ( $sub_long & $mask );
	}

	// ── 私有辅助 ────────────────────────────────────────────────────────────

	/**
	 * 校验字符串是否是合法 IPv4 或 IPv6 地址。
	 *
	 * @param string $ip
	 * @return bool
	 */
	private static function is_valid_ip( $ip ) {
		return false !== filter_var( $ip, FILTER_VALIDATE_IP );
	}

	/**
	 * 判断 peer IP 是否在可信代理 CIDR 范围内。
	 *
	 * @param string $peer REMOTE_ADDR。
	 * @return bool
	 */
	private static function ip_in_trusted_proxy( $peer ) {
		if ( ! $peer ) {
			return false;
		}
		foreach ( self::$trusted_proxy_cidrs as $cidr ) {
			if ( self::ip_in_range( $peer, $cidr ) ) {
				return true;
			}
		}
		return false;
	}
}
