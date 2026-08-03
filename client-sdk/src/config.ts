/** SDK 配置。
 *
 * 与 V1 的差异：
 * - 去掉 `siteId`（V2 只有 `appId` 一个租户维度）。
 * - `appSecret` 取代 `apiKey` 作为签名密钥；`apiKey` 只走 header 做身份识别。
 * - 路径前缀由 `/v1` 变为 `/v2`。
 */

export interface SdkConfig {
  /** Gateway API 基址。反代传 `/api`，直连传 `http://host:8000`。 */
  apiBase: string;
  /** 请求超时（毫秒）。 */
  apiTimeout: number;
  /** API Key，走 `X-App-Key` header。 */
  apiKey: string;
  /**
   * 签名密钥。
   *
   * 只在站点开启 `signature_required` 时需要。**放在浏览器里等于公开**，
   * 因此仅适用于「防止第三方伪造画像」而非「防止本站用户伪造」的场景；
   * 真正需要保密签名的接入应走 Adapter 路径（服务端签名）。
   */
  appSecret: string;
  /** 应用 ID，必填。 */
  appId: number;
  /** SDK 版本，随 init/heartbeat 上报。 */
  sdkVersion: string;
  /** Evercookie 写入重试次数。 */
  retryCount: number;
  /** 重试间隔（毫秒）。 */
  retryDelay: number;
  /** 启用的存储通道。 */
  storageTypes: string[];
  /** 是否采集浏览器指纹。 */
  collectFingerprint: boolean;
  /** 是否采集行为时序。 */
  collectBehavior: boolean;
  /** 是否允许访问第三方域名做 AdBlock 探测。默认关闭（隐私）。 */
  thirdPartyProbe: boolean;
  /** 是否自动执行返回的处置（跳转 / 渲染替代页 / 拦截）。 */
  autoApply: boolean;
  /** 调试日志。 */
  debug: boolean;
  /** 心跳间隔（毫秒），行为事件随心跳上报。 */
  heartbeatInterval: number;
  /** 配置版本轮询间隔（毫秒）。 */
  syncInterval: number;
  /** init 配置本地缓存有效期（毫秒）。 */
  initCacheTtl: number;
}

export const defaultConfig: SdkConfig = {
  apiBase: '',
  apiTimeout: 5000,
  apiKey: '',
  appSecret: '',
  appId: 0,
  sdkVersion: '2.0.0',
  retryCount: 3,
  retryDelay: 300,
  storageTypes: [
    'cookie',
    'localStorage',
    'sessionStorage',
    'indexedDB',
    'windowName',
    'cacheStorage',
  ],
  collectFingerprint: true,
  collectBehavior: true,
  thirdPartyProbe: false,
  autoApply: true,
  debug: false,
  heartbeatInterval: 60000,
  syncInterval: 120000,
  initCacheTtl: 86400000,
};

/** V2 端点路径。集中在此，避免散落拼接出 `/v2/v2/*`。 */
export const ENDPOINTS = {
  decide: '/v2/decide',
  decideFast: '/v2/decide/fast',
  sdkInit: '/v2/sdk/init',
  sdkStatus: '/v2/sdk/status',
  sdkHeartbeat: '/v2/sdk/heartbeat',
  challengeVerify: '/v2/challenge/verify',
} as const;
