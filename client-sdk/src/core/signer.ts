/** 请求签名。
 *
 * 待签串构造必须与 `fangyu_shared.utils.crypto.build_sign_payload` 逐字节一致，
 * 否则网关验签必然失败。两侧的一致性由 `tests/fixtures/sign_vectors.json`
 * 锁定——该文件同时被 Python 的 `test_sign_payload_parity.py` 与本目录的
 * `signer.test.ts` 读取。**改动任一侧的实现都必须让两个测试同时通过。**
 */

import { bufferToHex, canonicalJson, hmacSha256 } from '../utils/crypto';

/** 不参与签名的字段。对齐 Python `_SIGN_EXCLUDED_KEYS`。 */
const EXCLUDED_KEYS = new Set(['sign']);

/**
 * URL 编码，对齐 Python `quote(s, safe="-_.!~*'()")`。
 *
 * `encodeURIComponent` 的默认保留集恰好是 `A-Za-z0-9-_.!~*'()`，与 Python 侧
 * 显式指定的 safe 集完全相同——包括把 `/` 编码成 `%2F`、空格编码成 `%20`
 * （不是 `+`）。因此不需要任何差异映射。
 */
function signEncode(value: string): string {
  return encodeURIComponent(value);
}

/**
 * 把单个值转成待签字符串。对齐 Python `_sign_value`。
 *
 * - `boolean` → 小写 `"true"` / `"false"`（Python `str(True)` 是 `"True"`，
 *   所以 Python 侧也做了同样的特判）。
 * - `object` / `array` → 键排序的紧凑 JSON。
 * - 其余 → `String(value)`。
 */
function signValue(value: unknown): string {
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (value !== null && typeof value === 'object') {
    return canonicalJson(value);
  }
  return String(value);
}

/**
 * 构造待签串：键字典序 → URL 编码 → `k=v&k=v`。
 *
 * `null` / `undefined` / 空字符串一并剔除——各接入方（PHP / Lua / JS）对
 * 「字段缺失」与「字段为空串」的表达不统一，参与签名会导致同一请求算出
 * 不同签名。注意 `0` 和 `false` **保留**（它们是有效取值，不是缺失）。
 */
export function buildSignPayload(params: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of Object.keys(params).sort()) {
    if (EXCLUDED_KEYS.has(key)) continue;
    const value = params[key];
    if (value === null || value === undefined || value === '') continue;
    parts.push(`${signEncode(key)}=${signEncode(signValue(value))}`);
  }
  return parts.join('&');
}

/** 对参数字典生成 HMAC-SHA256 签名。 */
export async function signParams(
  params: Record<string, unknown>,
  secret: string,
): Promise<string> {
  return hmacSha256(secret, buildSignPayload(params));
}

/** 生成 32 位十六进制随机 nonce。对齐 Python `secrets.token_hex(16)` 的形状。 */
export function generateNonce(): string {
  const arr = new Uint8Array(16);
  globalThis.crypto.getRandomValues(arr);
  return bufferToHex(arr.buffer);
}
