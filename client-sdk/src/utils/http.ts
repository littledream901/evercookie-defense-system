/** HTTP 通信。fetch + AbortController 实现超时。
 *
 * 刻意不设 `credentials: 'include'`：
 * 网关鉴权走 `X-App-Key` 头，从不下发 Cookie（gateway-api 全局无 set_cookie）；
 * Evercookie 的 cookie 通道写的是接入方自己域名下的 document.cookie，跨域请求
 * 网关时本就带不过去。而一旦开启 credentials 模式，浏览器会拒收
 * `Access-Control-Allow-Origin: *` 的响应——SDK 的接入源无法预先枚举，网关
 * 默认正是通配源，两者冲突会让所有跨站请求直接失败。
 * 注意 curl 不模拟 credentials 模式，用 curl 测预检永远是 200，复现不出该问题。
 */

export interface HttpResponse<T = unknown> {
  ok: boolean;
  data: T | null;
  status: number;
  error?: string;
}

export interface RequestOptions {
  timeout?: number;
  /** API Key，写入 `X-App-Key` header。 */
  apiKey?: string;
}

const DEFAULT_TIMEOUT = 5000;

function buildHeaders(apiKey: string | undefined, json: boolean): HeadersInit {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (json) {
    headers['Content-Type'] = 'application/json;charset=utf-8';
  }
  if (apiKey) {
    headers['X-App-Key'] = apiKey;
  }
  return headers;
}

async function request<T>(url: string, init: RequestInit, timeout: number): Promise<HttpResponse<T>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(timer);

    let body: T | null = null;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        body = (await response.json()) as T;
      } catch {
        // body 保持 null——网关返回了声明为 JSON 的坏载荷，交由调用方兜底
      }
    }

    return { ok: response.ok, data: body, status: response.status };
  } catch (err) {
    clearTimeout(timer);
    const error = err as { name?: string; message?: string };
    if (error.name === 'AbortError') {
      return { ok: false, data: null, status: 0, error: '请求超时' };
    }
    return { ok: false, data: null, status: 0, error: error.message || '网络错误' };
  }
}

export async function post<T = unknown>(
  url: string,
  data: object,
  options: RequestOptions = {},
): Promise<HttpResponse<T>> {
  return request<T>(
    url,
    {
      method: 'POST',
      headers: buildHeaders(options.apiKey, true),
      body: JSON.stringify(data),
    },
    options.timeout ?? DEFAULT_TIMEOUT,
  );
}

export async function get<T = unknown>(
  url: string,
  options: RequestOptions = {},
): Promise<HttpResponse<T>> {
  return request<T>(
    url,
    {
      method: 'GET',
      headers: buildHeaders(options.apiKey, false),
    },
    options.timeout ?? DEFAULT_TIMEOUT,
  );
}
