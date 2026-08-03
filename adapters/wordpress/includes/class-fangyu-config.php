<?php
/**
 * 配置管理：从 WP 选项读写网关连接参数。
 *
 * 与参考插件的差异
 * ----------------
 * 旧版用 PHP 常量（`define('FANGYU_API_KEY', ...)`），部署时要直接编辑
 * `wp-config.php`，非技术用户操作困难，且常量改完需要重新 require 才生效。
 * 本版全部存 WP options，可在后台表单里修改，改完立即生效。
 *
 * 选项键全部加前缀 `fangyu_` 避免与其他插件冲突。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 静态配置读写封装。
 */
class Fangyu_Config {

	/** @var string WP options 前缀 */
	const PREFIX = 'fangyu_';

	/** @var string[] 允许的失败模式 */
	const FAIL_MODES = array( 'open', 'closed' );

	/**
	 * 读取网关基础 URL。
	 *
	 * @return string 末尾不含斜杠，例如 `https://defense.example.com`。
	 */
	public static function gateway_url() {
		return rtrim( (string) get_option( self::PREFIX . 'gateway_url', '' ), '/' );
	}

	/**
	 * 读取站点 ID（同时用作 X-App-Key 请求头）。
	 *
	 * 格式 site_<hex8>，从 Fangyu 管理后台「站点管理」页面复制。
	 *
	 * @return string 未配置时返回空串。
	 */
	public static function site_id() {
		return (string) get_option( self::PREFIX . 'site_id', '' );
	}

	/**
	 * @deprecated 使用 site_id() 替代
	 * @return string
	 */
	public static function api_key() {
		// 兼容旧选项；新安装写的是 site_id，升级时两者可能都存在。
		$legacy = (string) get_option( self::PREFIX . 'api_key', '' );
		return $legacy ?: self::site_id();
	}

	/**
	 * 读取应用 ID。
	 *
	 * 格式为整数（例如 1001），从 Fangyu 管理后台「站点管理」页面获取。
	 *
	 * @return int 未配置时返回 0。
	 */
	public static function app_id() {
		return (int) get_option( self::PREFIX . 'app_id', 0 );
	}

	/**
	 * 读取签名密钥（`app_secret`）。
	 *
	 * 只在本地用于计算 HMAC，**不通过网络发送**。
	 *
	 * @return string 未配置时返回空串。
	 */
	public static function app_secret() {
		return (string) get_option( self::PREFIX . 'app_secret', '' );
	}

	/**
	 * 网关不可达时的失败模式。
	 *
	 * `open`   — 放行（默认；避免误杀正常流量）。
	 * `closed` — 拦截（高安全场景；网关挂了等于全站拦截）。
	 *
	 * @return string 'open' 或 'closed'。
	 */
	public static function fail_mode() {
		$mode = (string) get_option( self::PREFIX . 'fail_mode', 'open' );
		return in_array( $mode, self::FAIL_MODES, true ) ? $mode : 'open';
	}

	/**
	 * 插件是否已完整配置（最少需要这三项）。
	 *
	 * @return bool
	 */
	public static function is_configured() {
		return self::gateway_url() !== ''
			&& self::site_id() !== ''
			&& self::app_secret() !== '';
	}

	/**
	 * 批量保存表单提交的配置。
	 *
	 * @param array $raw $_POST 原始数据（已经过 nonce 校验）。
	 * @return void
	 */
	public static function save( array $raw ) {
		$fields = array(
			'gateway_url' => 'esc_url_raw',
			'site_id'     => 'sanitize_text_field',
			'app_id'      => 'absint',
			'app_secret'  => 'sanitize_text_field',
			'fail_mode'   => 'sanitize_text_field',
		);
		foreach ( $fields as $key => $sanitizer ) {
			if ( ! isset( $raw[ $key ] ) ) {
				continue;
			}
			$value = call_user_func( $sanitizer, $raw[ $key ] );
			if ( 'fail_mode' === $key && ! in_array( $value, self::FAIL_MODES, true ) ) {
				$value = 'open';
			}
			if ( 'gateway_url' === $key ) {
				$value = rtrim( $value, '/' );
			}
			update_option( self::PREFIX . $key, $value );
		}
	}

	/**
	 * 删除所有插件选项（卸载时调用）。
	 *
	 * @return void
	 */
	public static function delete_all() {
		foreach ( array( 'gateway_url', 'site_id', 'app_id', 'app_secret', 'fail_mode', 'api_key' ) as $key ) {
			delete_option( self::PREFIX . $key );
		}
	}
}
