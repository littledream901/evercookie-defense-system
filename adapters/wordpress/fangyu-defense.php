<?php
/**
 * Plugin Name: Fangyu Defense
 * Plugin URI:  https://github.com/your-org/evercookie-defense-system
 * Description: V2 anti-bot / visitor defense powered by the Fangyu gateway.
 *              Uses evercookie-based fingerprinting and HMAC-signed adapter requests.
 * Version:     2.0.0
 * Author:      Fangyu Team
 * License:     GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: fangyu-defense
 * Domain Path: /languages
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** 插件主文件路径，供 executor 构造 assets URL 使用。 */
define( 'FANGYU_DEFENSE_FILE', __FILE__ );

/** 插件版本。 */
define( 'FANGYU_DEFENSE_VERSION', '2.0.0' );

// ── 自动加载 ──────────────────────────────────────────────────────────────

$includes = array(
	'class-fangyu-config.php',
	'class-fangyu-signer.php',
	'class-fangyu-visitor.php',
	'class-fangyu-client.php',
	'class-fangyu-executor.php',
	'class-fangyu-admin.php',
);
foreach ( $includes as $file ) {
	require_once plugin_dir_path( __FILE__ ) . 'includes/' . $file;
}

// ── 激活 / 停用 / 卸载 ────────────────────────────────────────────────────

register_activation_hook( __FILE__, 'fangyu_defense_activate' );
register_deactivation_hook( __FILE__, 'fangyu_defense_deactivate' );
register_uninstall_hook( __FILE__, 'fangyu_defense_uninstall' );

/**
 * 激活：不做数据库操作，选项按需写入（WP options 无需建表）。
 *
 * @return void
 */
function fangyu_defense_activate() {
	// 设置缺省 fail_mode 为 open，避免未配置时白屏。
	if ( false === get_option( 'fangyu_fail_mode' ) ) {
		add_option( 'fangyu_fail_mode', 'open' );
	}
}

/**
 * 停用：保留选项，方便重新激活后恢复配置。
 *
 * @return void
 */
function fangyu_defense_deactivate() {
	// no-op
}

/**
 * 卸载：删除所有选项。
 *
 * @return void
 */
function fangyu_defense_uninstall() {
	Fangyu_Config::delete_all();
}

// ── 后台 ─────────────────────────────────────────────────────────────────

if ( is_admin() ) {
	Fangyu_Admin::register_hooks();
}

// ── 前台防护主钩子 ────────────────────────────────────────────────────────

add_action( 'template_redirect', 'fangyu_defense_check', 1 );

/**
 * 前台请求拦截点。
 *
 * 优先级 1（最早执行）确保在主题渲染前完成处置；这样 `wp_redirect` 等头才能
 * 在任何输出之前发出，避免 "headers already sent" 警告。
 *
 * 跳过的场景：
 *   - WP-CLI / cron：非 HTTP 请求，不需要防护。
 *   - WP REST API 管理端点（`/wp-json/wp/v2/users` 等）：不在保护范围内，
 *     避免误伤 Gutenberg 编辑器的 AJAX 调用。
 *   - 已登录的管理员：防止错误规则把自己锁在门外。
 *   - 未配置：未填网关地址时静默放行（fail-open 精神）。
 *   - `wp-cron.php` / `xmlrpc.php`：WordPress 内部端点，不需要用户态防护。
 *
 * @return void
 */
function fangyu_defense_check() {
	// 跳过 CLI / CRON 环境。
	if ( defined( 'WP_CLI' ) && WP_CLI ) {
		return;
	}
	if ( defined( 'DOING_CRON' ) && DOING_CRON ) {
		return;
	}

	// 跳过后台页面（包括 ajax）。
	if ( is_admin() ) {
		return;
	}

	// 跳过已登录管理员，防止配置错误时自我锁定。
	if ( current_user_can( 'manage_options' ) ) {
		return;
	}

	// 未完整配置时静默放行。
	if ( ! Fangyu_Config::is_configured() ) {
		return;
	}

	$ip          = Fangyu_Visitor::get_client_ip();
	$fingerprint = Fangyu_Visitor::get_repeat_value();
	$visit_url   = Fangyu_Visitor::get_page_url();
	$user_agent  = isset( $_SERVER['HTTP_USER_AGENT'] )
		? sanitize_text_field( wp_unslash( $_SERVER['HTTP_USER_AGENT'] ) )
		: '';
	$referer     = Fangyu_Visitor::get_referer();

	$context = array(
		'appId'        => Fangyu_Config::app_id(),
		'ingress'      => 'adapter',
		'ip'           => $ip,
		'fingerprint'  => $fingerprint ?: null,
		'visitUrl'     => $visit_url,
		'userAgent'    => $user_agent,
		'repeatKey'    => Fangyu_Visitor::DEFAULT_REPEAT_KEY,
		'repeatValue'  => $fingerprint ?: null,
		'referer'      => $referer ?: null,
	);

	// 移除 null 值（与 build_sign_payload 的 null 剔除规则一致）。
	$context = array_filter(
		$context,
		static function ( $v ) {
			return null !== $v && '' !== $v;
		}
	);

	$result = Fangyu_Client::decide( $context );

	// 第一层已拦截：直接执行处置，SDK 不加载
	if ( Fangyu_Executor::execute( $result ) ) {
		return;
	}

	// 第一层 pass：放行并注入 SDK + __fy_server_ctx（hybrid 模式）
	// fallback 时 server_token 为 null，SDK 将以 standalone 模式运行
	Fangyu_Executor::schedule_sdk_injection( $result );
}
