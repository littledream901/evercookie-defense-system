/** 哈希与规范化序列化工具。 */

/** DJB2 快速字符串哈希，用于生成轻量指纹标识。 */
export function djb2Hash(str: string): string {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
}

/** 将 ArrayBuffer 转成十六进制串。 */
export function bufferToHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let hex = '';
  for (let i = 0; i < bytes.length; i++) {
    hex += (bytes[i] as number).toString(16).padStart(2, '0');
  }
  return hex;
}

/** 取 WebCrypto 实例。jsdom 与浏览器都走 globalThis.crypto。 */
function subtle(): SubtleCrypto {
  const c = globalThis.crypto;
  if (!c || !c.subtle) {
    throw new Error('WebCrypto 不可用：SDK 需要 HTTPS 或 localhost 环境');
  }
  return c.subtle;
}

/** SHA-256 摘要（十六进制）。 */
export async function sha256(str: string): Promise<string> {
  const data = new TextEncoder().encode(str);
  const digest = await subtle().digest('SHA-256', data);
  return bufferToHex(digest);
}

/** HMAC-SHA256（十六进制）。 */
export async function hmacSha256(secret: string, message: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await subtle().importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signature = await subtle().sign('HMAC', key, encoder.encode(message));
  return bufferToHex(signature);
}

/**
 * 规范化 JSON 序列化：递归按键排序 + 紧凑分隔符。
 *
 * 逐字节对齐 Python 侧的
 * `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`。
 *
 * 已知的不可对齐点（调用方必须规避，不在此处兜底）：
 * - **浮点数**：Python `1.0` 序列化成 `"1.0"`，JS 序列化成 `"1"`。因此参与
 *   签名的数值一律取整（见 `BehaviorScalar` 的注释）。
 * - **undefined**：JS 对象里的 `undefined` 值会被 `JSON.stringify` 丢弃，
 *   Python 侧没有对应概念。这里显式跳过，与 stringify 行为一致。
 */
export function canonicalJson(value: unknown): string {
  return JSON.stringify(sortDeep(value));
}

function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(sortDeep);
  }
  if (value !== null && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) {
      const item = source[key];
      if (item === undefined) continue;
      sorted[key] = sortDeep(item);
    }
    return sorted;
  }
  return value;
}
