<?php
/**
 * HMAC-SHA256 请求签名。
 *
 * 与 Python 端 `fangyu_shared.security.signing.build_sign_payload`、
 * TS 端 `client-sdk/src/core/signer.ts` 三方逐字节对齐。三份实现的一致性由
 * `client-sdk/tests/fixtures/sign_vectors.json` 锁定，本文件的 PHP 实现由
 * `tests/parity/sign_parity_test.php` 跑同一份向量验证。
 *
 * 为什么不能抄参考插件
 * --------------------
 * 旧版 `fangyu-php-full` 的 `getSign()` 是：
 *   hash('sha256', http_build_query($params) . FANGYU_API_KEY)
 * 两处不兼容：
 *   1. 普通 SHA256 拼接 ≠ HMAC-SHA256。密钥拼在消息尾部的构造无法抵抗
 *      长度扩展类攻击，也不是网关校验的算法，验签必然 401。
 *   2. `http_build_query()` 默认 RFC1738，空格编码成 `+`；网关按 `%20`。
 *
 * 为什么也不能照计划里的 PHP_QUERY_RFC3986
 * ---------------------------------------
 * 实施计划写的是 `http_build_query($p, '', '&', PHP_QUERY_RFC3986)`，这个方案
 * 在 5 个字符上与网关不一致，会造成**间歇性**验签失败——只有当参数值恰好含
 * 这些字符时才 401，最难定位：
 *
 *   | 字符      | rawurlencode / RFC3986 | Python quote(safe="-_.!~*'()") | encodeURIComponent |
 *   |-----------|------------------------|--------------------------------|--------------------|
 *   | ! * ' ( ) | %21 %2A %27 %28 %29    | 原样保留                        | 原样保留            |
 *
 * RFC3986 把 `!*'()` 归为 sub-delims 要求编码，而 JS 的 `encodeURIComponent`
 * 沿用更早的 RFC2396 unreserved 集合把它们放过。网关选择与 `encodeURIComponent`
 * 对齐（浏览器侧没法改写这个内置函数），所以 PHP 必须在 `rawurlencode` 之后
 * 把这 5 个字符解回来。向量 `reserved_chars_preserved`（token=-_.!~*'()）就是
 * 专门锁这一条的。
 *
 * 另外 `http_build_query` 本身还有两个不适配点，所以整个函数弃用不只是编码问题：
 *   - 它会把嵌套数组展开成 `a[b]=1` 形式，而网关要求嵌套结构走**紧凑排序
 *     JSON**（向量 `nested_dict_sorted_compact_json`）。
 *   - 它会静默丢弃 null，但保留不了 `false`（转成空串），而网关要求
 *     `false` → 字面量 `"false"`（向量 `bool_lowercase`）。
 *
 * @package FangyuDefense
 */

if ( ! defined( 'ABSPATH' ) && ! defined( 'FANGYU_PARITY_TEST' ) ) {
	exit;
}

/**
 * 签名构造器。
 */
class Fangyu_Signer {

	/**
	 * 不参与签名的键。
	 *
	 * `sign` 自身必须排除，否则第二次签名会把上一次的结果当输入。
	 *
	 * @var string[]
	 */
	const EXCLUDED_KEYS = array( 'sign' );

	/**
	 * `encodeURIComponent` 不编码、但 `rawurlencode` 会编码的字符。
	 *
	 * 键是 rawurlencode 的输出，值是要还原成的原字符。
	 *
	 * @var array<string,string>
	 */
	const ENCODE_EXCEPTIONS = array(
		'%21' => '!',
		'%2A' => '*',
		'%27' => "'",
		'%28' => '(',
		'%29' => ')',
	);

	/**
	 * 百分号编码，语义等价于 JS `encodeURIComponent`。
	 *
	 * @param string $value 原始值（UTF-8）。
	 * @return string 编码结果。
	 */
	public static function encode_component( $value ) {
		$encoded = rawurlencode( (string) $value );
		return strtr( $encoded, self::ENCODE_EXCEPTIONS );
	}

	/**
	 * 递归按键排序，供 JSON 序列化使用。
	 *
	 * 列表**保序**：数组顺序本身是语义（如行为事件的时序），排序会改变含义。
	 * 只有关联数组（对象）才排序。
	 *
	 * @param mixed $value 任意值。
	 * @return mixed 排序后的值。
	 */
	private static function sort_deep( $value ) {
		if ( is_array( $value ) ) {
			if ( self::is_list( $value ) ) {
				return array_map( array( __CLASS__, 'sort_deep' ), $value );
			}
			ksort( $value, SORT_STRING );
			$out = array();
			foreach ( $value as $key => $item ) {
				if ( null === $item ) {
					// Python json.dumps 会输出 null，此处保留以对齐；
					// 只有顶层参数才丢弃 null（见 build_payload）。
					$out[ (string) $key ] = null;
					continue;
				}
				$out[ (string) $key ] = self::sort_deep( $item );
			}
			return $out;
		}
		if ( is_object( $value ) ) {
			return self::sort_deep( get_object_vars( $value ) );
		}
		return $value;
	}

	/**
	 * 判断是否为「列表」（连续 0..n-1 整数键）。
	 *
	 * PHP 8.1 有 `array_is_list()`，但 WordPress 仍支持 PHP 7.4，
	 * 这里自己实现以免在旧站点上直接白屏。
	 *
	 * @param array $value 数组。
	 * @return bool 是否列表。
	 */
	private static function is_list( array $value ) {
		if ( function_exists( 'array_is_list' ) ) {
			return array_is_list( $value );
		}
		$i = 0;
		foreach ( $value as $key => $_unused ) {
			if ( $key !== $i ) {
				return false;
			}
			++$i;
		}
		return true;
	}

	/**
	 * 紧凑排序 JSON，对齐 Python
	 * `json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`。
	 *
	 * `JSON_UNESCAPED_SLASHES` 必须给：PHP 默认把 `/` 转义成 `\/`，Python 不转。
	 * `JSON_UNESCAPED_UNICODE` 对应 `ensure_ascii=False`。
	 *
	 * @param mixed $value 任意值。
	 * @return string JSON 串。
	 */
	public static function canonical_json( $value ) {
		$sorted = self::sort_deep( $value );
		// json_encode flags:
		//   JSON_UNESCAPED_SLASHES — PHP 默认把 `/` 转义成 `\/`，Python 不转，不加此标志
		//                            就会让所有含斜杠的 URL 签名失败。
		//   JSON_UNESCAPED_UNICODE — 对应 Python json.dumps(ensure_ascii=False)；
		//                            不加此标志汉字会变成 \uXXXX，与 Python 输出不同。
		// wp_json_encode() 只是 json_encode 的一个 WP 兼容包装，底层相同；
		// 这里直接调 json_encode 以便在 WP 之外（如 parity test）也能使用。
		$json = json_encode( $sorted, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );
		return false === $json ? '' : $json;
	}

	/**
	 * 单个值转字符串。
	 *
	 * bool 必须显式处理：PHP 的 `(string) true` 是 `"1"`、`(string) false` 是
	 * `""`，直接强转会同时破坏「true → 'true'」和「false 必须保留」两条规则。
	 *
	 * @param mixed $value 任意标量或结构。
	 * @return string 字符串形式。
	 */
	public static function stringify( $value ) {
		if ( is_bool( $value ) ) {
			return $value ? 'true' : 'false';
		}
		if ( is_array( $value ) || is_object( $value ) ) {
			return self::canonical_json( $value );
		}
		if ( is_float( $value ) ) {
			// 浮点跨语言不可靠：Python 出 "1.0"，JS 出 "1"。约定数值一律用整数，
			// 这里做整数化兜底而不是静默产出不可验签的字符串。
			if ( floor( $value ) === $value && abs( $value ) < 1.0e15 ) {
				return (string) (int) $value;
			}
			return (string) $value;
		}
		return (string) $value;
	}

	/**
	 * 构造待签名字符串。
	 *
	 * 规则（与 Python 端逐条对应）：
	 *   1. 键按字典序（字节序）排列，不是插入序；
	 *   2. `sign` 排除；
	 *   3. null 与空串剔除，`0` 与 `false` 保留；
	 *   4. 键与值分别百分号编码后以 `=` 连接，用 `&` 拼接。
	 *
	 * @param array $params 顶层参数。
	 * @return string 待签名串。
	 */
	public static function build_payload( array $params ) {
		$keys = array_map( 'strval', array_keys( $params ) );
		sort( $keys, SORT_STRING );

		$parts = array();
		foreach ( $keys as $key ) {
			if ( in_array( $key, self::EXCLUDED_KEYS, true ) ) {
				continue;
			}
			$value = $params[ $key ];
			if ( null === $value || '' === $value ) {
				continue;
			}
			$parts[] = self::encode_component( $key ) . '=' .
				self::encode_component( self::stringify( $value ) );
		}
		return implode( '&', $parts );
	}

	/**
	 * 计算签名。
	 *
	 * @param array  $params     顶层参数（不含 sign）。
	 * @param string $app_secret 应用密钥。
	 * @return string 小写十六进制 HMAC-SHA256。
	 */
	public static function sign( array $params, $app_secret ) {
		return hash_hmac( 'sha256', self::build_payload( $params ), (string) $app_secret );
	}

	/**
	 * 给请求体附加 `timestamp` / `nonce` / `sign` 三个顶层字段。
	 *
	 * 三个字段必须在**顶层**，与 `context` 平级。网关的 `_signable_params()`
	 * 只读顶层键；塞进 `context` 里签名串会完全不同，且因为 pydantic 默认
	 * `extra="ignore"` 不会报错，只会静默 401——这是最容易踩且最难查的错法。
	 *
	 * @param array  $body       请求体（含 context 等）。
	 * @param string $app_secret 应用密钥。
	 * @return array 附加签名字段后的请求体。
	 */
	public static function sign_body( array $body, $app_secret ) {
		$body['timestamp'] = time();
		$body['nonce']     = self::nonce();
		$body['sign']      = self::sign( $body, $app_secret );
		return $body;
	}

	/**
	 * 生成 32 位十六进制随机 nonce。
	 *
	 * 优先用 CSPRNG。`mt_rand` 兜底是为了在极老/极简 PHP 环境上不致直接抛异常
	 * 让整站白屏——nonce 只需防重放窗口内不撞，不承担机密性。
	 *
	 * @return string 32 字符十六进制串。
	 */
	public static function nonce() {
		if ( function_exists( 'random_bytes' ) ) {
			try {
				return bin2hex( random_bytes( 16 ) );
			} catch ( Exception $e ) { // phpcs:ignore Generic.CodeAnalysis.EmptyStatement
				// 熵源不可用，落到下面的兜底。
			}
		}
		$out = '';
		for ( $i = 0; $i < 32; $i++ ) {
			$out .= dechex( mt_rand( 0, 15 ) );
		}
		return $out;
	}
}
