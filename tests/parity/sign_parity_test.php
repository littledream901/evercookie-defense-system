<?php
/**
 * PHP 签名奇偶性测试。
 *
 * 针对 `client-sdk/tests/fixtures/sign_vectors.json` 中每一条向量，
 * 验证 PHP 实现与 Python / TS 端产出相同的 payload 字符串与 HMAC 值。
 *
 * 独立运行（不依赖 WordPress 或任何框架）：
 *
 *   php tests/parity/sign_parity_test.php
 *
 * 从 V2 目录（Evercookie Defense System V2/）执行；
 * 成功时退出码 0，失败时打印差异并以退出码 1 退出。
 *
 * @package FangyuDefense
 */

define( 'FANGYU_PARITY_TEST', true );

require_once __DIR__ . '/../../adapters/wordpress/includes/class-fangyu-signer.php';

$vectors_path = __DIR__ . '/../../client-sdk/tests/fixtures/sign_vectors.json';
if ( ! file_exists( $vectors_path ) ) {
	fwrite( STDERR, "向量文件不存在：{$vectors_path}\n" );
	exit( 1 );
}

$data    = json_decode( file_get_contents( $vectors_path ), true );
$secret  = $data['secret'];
$vectors = $data['vectors'];
$passed  = 0;
$failed  = 0;

foreach ( $vectors as $v ) {
	$name           = $v['name'];
	$params         = $v['params'];
	$expected_pay   = $v['payload'];
	$expected_sign  = $v['sign'];

	$actual_pay  = Fangyu_Signer::build_payload( $params );
	$actual_sign = Fangyu_Signer::sign( $params, $secret );

	$pay_ok  = ( $actual_pay === $expected_pay );
	$sign_ok = ( $actual_sign === $expected_sign );

	if ( $pay_ok && $sign_ok ) {
		echo "PASS  {$name}\n";
		++$passed;
	} else {
		echo "FAIL  {$name}\n";
		if ( ! $pay_ok ) {
			echo "  payload expected : {$expected_pay}\n";
			echo "  payload actual   : {$actual_pay}\n";
		}
		if ( ! $sign_ok ) {
			echo "  sign   expected  : {$expected_sign}\n";
			echo "  sign   actual    : {$actual_sign}\n";
		}
		++$failed;
	}
}

echo "\n{$passed} passed, {$failed} failed\n";
exit( $failed > 0 ? 1 : 0 );
