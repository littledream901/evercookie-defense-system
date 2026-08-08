<?php
/**
 * 后台设置页与连通性自检。
 *
 * 注册在「设置」菜单下（Settings > Fangyu Defense）。
 * 提供两个功能：
 *   1. 持久化网关连接参数（gateway_url / site_key / site_id / site_secret / fail_mode）。
 *   2. 「连通性自检」AJAX 按钮：向网关发一个签名完整的 `/v2/decide` 请求并
 *      展示返回码，用于确认密钥和地址填写正确。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * 设置页注册与渲染。
 */
class Fangyu_Admin {

	/** @var string 设置表单 nonce action。 */
	const NONCE_ACTION = 'fangyu_save_settings';

	/** @var string 自检 AJAX action。 */
	const CHECK_ACTION = 'fangyu_connectivity_check';

	/**
	 * 注册所有钩子（由主插件文件调用）。
	 *
	 * @return void
	 */
	public static function register_hooks() {
		add_action( 'admin_menu', array( __CLASS__, 'add_menu' ) );
		add_action( 'admin_init', array( __CLASS__, 'handle_save' ) );
		add_action( 'wp_ajax_' . self::CHECK_ACTION, array( __CLASS__, 'ajax_check' ) );
		add_action( 'admin_enqueue_scripts', array( __CLASS__, 'enqueue_scripts' ) );
	}

	/**
	 * 注册设置页菜单。
	 *
	 * @return void
	 */
	public static function add_menu() {
		add_options_page(
			__( 'Fangyu Defense Settings', 'fangyu-defense' ),
			__( 'Fangyu Defense', 'fangyu-defense' ),
			'manage_options',
			'fangyu-defense',
			array( __CLASS__, 'render_page' )
		);
	}

	/**
	 * 处理表单保存（POST 请求）。
	 *
	 * @return void
	 */
	public static function handle_save() {
		if ( ! isset( $_POST['fangyu_nonce'] ) ) {
			return;
		}
		if ( ! check_admin_referer( self::NONCE_ACTION, 'fangyu_nonce' ) ) {
			wp_die( esc_html__( 'Security check failed.', 'fangyu-defense' ) );
		}
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Insufficient permissions.', 'fangyu-defense' ) );
		}
		Fangyu_Config::save( $_POST ); // phpcs:ignore WordPress.Security.NonceVerification.Missing
		wp_redirect( admin_url( 'options-general.php?page=fangyu-defense&saved=1' ) );
		exit;
	}

	/**
	 * 加载设置页所需 JS（内联，不独立打包）。
	 *
	 * @param string $hook 当前 admin 页面钩子名。
	 * @return void
	 */
	public static function enqueue_scripts( $hook ) {
		if ( 'settings_page_fangyu-defense' !== $hook ) {
			return;
		}
		wp_add_inline_script(
			'jquery',
			self::check_inline_js(),
			'after'
		);
	}

	/**
	 * 渲染设置页 HTML。
	 *
	 * @return void
	 */
	public static function render_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'Insufficient permissions.', 'fangyu-defense' ) );
		}
		$saved = isset( $_GET['saved'] );
		?>
		<div class="wrap">
			<h1><?php esc_html_e( 'Fangyu Defense Settings', 'fangyu-defense' ); ?></h1>

			<?php if ( $saved ) : ?>
			<div class="notice notice-success is-dismissible">
				<p><?php esc_html_e( 'Settings saved.', 'fangyu-defense' ); ?></p>
			</div>
			<?php endif; ?>

			<form method="post" action="">
				<?php wp_nonce_field( self::NONCE_ACTION, 'fangyu_nonce' ); ?>
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row">
							<label for="gateway_url"><?php esc_html_e( 'Gateway URL', 'fangyu-defense' ); ?></label>
						</th>
						<td>
							<input type="url" id="gateway_url" name="gateway_url"
								value="<?php echo esc_url( Fangyu_Config::gateway_url() ); ?>"
								class="regular-text" placeholder="https://defense.example.com" />
							<p class="description">
								<?php esc_html_e( 'Base URL of the Fangyu V2 gateway, without trailing slash.', 'fangyu-defense' ); ?>
							</p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="site_key"><?php esc_html_e( 'Site Key', 'fangyu-defense' ); ?></label>
						</th>
						<td>
							<input type="text" id="site_key" name="site_key"
								value="<?php echo esc_attr( Fangyu_Config::site_key() ); ?>"
								class="regular-text" autocomplete="off"
								placeholder="site_xxxxxxxx" />
							<p class="description">
								<?php esc_html_e( 'Site key (format: site_<hex8>). Sent as the X-App-Key request header. Copy from the Fangyu admin dashboard → Sites.', 'fangyu-defense' ); ?>
							</p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="site_id"><?php esc_html_e( 'Site ID', 'fangyu-defense' ); ?></label>
						</th>
						<td>
							<input type="number" id="site_id" name="site_id" min="1" step="1"
								value="<?php echo esc_attr( (string) Fangyu_Config::site_id() ); ?>"
								class="regular-text" autocomplete="off" placeholder="1001" />
							<p class="description">
								<?php esc_html_e( 'Numeric site ID (e.g., 1001). Used as the SDK siteId parameter and in decision context. Copy from the Fangyu admin dashboard → Sites.', 'fangyu-defense' ); ?>
							</p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="site_secret"><?php esc_html_e( 'Site Secret', 'fangyu-defense' ); ?></label>
						</th>
						<td>
							<input type="password" id="site_secret" name="site_secret"
								value="<?php echo esc_attr( Fangyu_Config::site_secret() ); ?>"
								class="regular-text" autocomplete="new-password" />
							<p class="description">
								<?php esc_html_e( 'Used to sign requests (HMAC-SHA256). Never transmitted to the gateway.', 'fangyu-defense' ); ?>
							</p>
						</td>
					</tr>
					<tr>
						<th scope="row"><?php esc_html_e( 'Fail Mode', 'fangyu-defense' ); ?></th>
						<td>
							<fieldset>
								<label>
									<input type="radio" name="fail_mode" value="open"
										<?php checked( Fangyu_Config::fail_mode(), 'open' ); ?> />
									<?php esc_html_e( 'Open — allow traffic when gateway is unreachable (recommended)', 'fangyu-defense' ); ?>
								</label><br>
								<label>
									<input type="radio" name="fail_mode" value="closed"
										<?php checked( Fangyu_Config::fail_mode(), 'closed' ); ?> />
									<?php esc_html_e( 'Closed — block traffic when gateway is unreachable (high-security mode)', 'fangyu-defense' ); ?>
								</label>
							</fieldset>
						</td>
					</tr>
				</table>

				<?php submit_button( __( 'Save Settings', 'fangyu-defense' ) ); ?>
			</form>

			<hr>
			<h2><?php esc_html_e( 'Connectivity Check', 'fangyu-defense' ); ?></h2>
			<p><?php esc_html_e( 'Sends a signed test request to the gateway to verify the connection and credentials.', 'fangyu-defense' ); ?></p>
			<button id="fangyu-check-btn" class="button button-secondary">
				<?php esc_html_e( 'Run Check', 'fangyu-defense' ); ?>
			</button>
			<span id="fangyu-check-result" style="margin-left:1em;font-weight:600"></span>
			<input type="hidden" id="fangyu-check-nonce"
				value="<?php echo esc_attr( wp_create_nonce( self::CHECK_ACTION ) ); ?>" />
		</div>
		<?php
	}

	/**
	 * AJAX 处理：执行连通性自检。
	 *
	 * @return void
	 */
	public static function ajax_check() {
		check_ajax_referer( self::CHECK_ACTION, 'nonce' );
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_send_json_error( array( 'message' => 'Insufficient permissions.' ), 403 );
		}

		if ( ! Fangyu_Config::is_configured() ) {
			wp_send_json_error( array( 'message' => 'Plugin is not fully configured.' ) );
		}

		// 构造一个最小的 adapter 风格请求，仅用于测试可达性与签名。
		// appId 由 gateway 根据 X-App-Key（site_key）自动解析，无需显式传递。
		$context = array(
			'ingress' => 'adapter',
			'ip'      => '127.0.0.1',
		);
		$result = Fangyu_Client::decide( $context );

		if ( $result->is_fallback ) {
			wp_send_json_error(
				array( 'message' => 'Gateway unreachable or request rejected. Check URL and credentials.' )
			);
		}
		wp_send_json_success(
			array(
				'message'   => 'OK — gateway responded.',
				'verdict'   => $result->verdict,
				'mechanism' => $result->mechanism,
			)
		);
	}

	/**
	 * 连通性检查按钮的内联 JS。
	 *
	 * @return string
	 */
	private static function check_inline_js() {
		$ajax_url = esc_js( admin_url( 'admin-ajax.php' ) );
		$action   = esc_js( self::CHECK_ACTION );
		return <<<JS
(function($){
  $('#fangyu-check-btn').on('click', function(){
    var \$btn = $(this);
    var \$res = $('#fangyu-check-result');
    var nonce = $('#fangyu-check-nonce').val();
    \$btn.prop('disabled', true);
    \$res.text('…').css('color','');
    $.post('{$ajax_url}', {action:'{$action}', nonce:nonce}, function(resp){
      if(resp.success){
        \$res.text('✓ ' + resp.data.message).css('color','green');
      } else {
        \$res.text('✗ ' + (resp.data && resp.data.message || 'Error')).css('color','red');
      }
    }).fail(function(){
      \$res.text('✗ Request failed').css('color','red');
    }).always(function(){
      \$btn.prop('disabled', false);
    });
  });
})(jQuery);
JS;
	}
}
