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
  /**
   * Hybrid 双层接入的第一层会话令牌。
   *
   * 由服务端适配器完成第一层判定后注入页面。SDK 随 `context.extra.serverToken`
   * 上报，网关的 HYBRID_LOOKUP 阶段凭此取出第一层结论。令牌一次性消费。
   * 纯 SDK 接入（无适配器）留空即可。
   */
  serverToken: string;
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
  /** Audio 指纹探针超时（毫秒）。见 `collectAll` 注释。 */
  audioTimeout: number;
  /**
   * 决策前读取存储通道的软上限（毫秒）。见 `ResolveOptions.deadlineMs`。
   *
   * 超时只影响**本次**取值，慢通道仍会在后台跑完并自愈，不损失 Evercookie
   * 的恢复能力。
   */
  storageDeadline: number;
  /**
   * `decide()` 等待 `init()` 的上限（毫秒）。
   *
   * 超过则**不再等**，init 转入后台继续跑。init 只提供 clockSkew 与行为策略，
   * 都不是决策的必要输入——串行等它等于把一整个 RTT 加在跳转前面。
   * 置 0 表示完全不等。
   */
  initDeadline: number;
  /**
   * 指纹 id 本地缓存有效期（毫秒）。0 表示禁用。
   *
   * 首访必须跑完整探针（canvas/webgl/audio 等）才能拿到指纹，这是 SDK 路径的
   * 硬性要求（网关对 `ingress=sdk` 强制校验非空指纹）。回访直接读缓存，
   * 关键路径上的探针开销归零。
   */
  fingerprintCacheTtl: number;
  /**
   * 决策结果的会话级缓存有效期上限（毫秒）。
   *
   * 实际 TTL 取 `min(服务端 ttlSeconds, 此值)`。命中缓存时可在 head 同步阶段
   * 直接执行处置，**零网络**。0 表示禁用缓存。
   */
  decisionCacheTtl: number;
  /**
   * 判定完成前是否隐藏页面内容。
   *
   * 默认 **false**：保证不影响正常访客的渲染流程。高价值页面（落地页、
   * 商品详情）可开启，配合 `hideTimeout` 兜底，避免 Bot 在判定完成前抓到内容。
   */
  hideUntilDecided: boolean;
  /** `hideUntilDecided` 的强制显示兜底时限（毫秒），防止网络差时白屏。 */
  hideTimeout: number;
}

export const defaultConfig: SdkConfig = {
  apiBase: '',
  apiTimeout: 5000,
  apiKey: '',
  appSecret: '',
  appId: 0,
  serverToken: '',
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
  audioTimeout: 800,
  storageDeadline: 30,
  initDeadline: 0,
  fingerprintCacheTtl: 86400000,
  decisionCacheTtl: 300000,
  hideUntilDecided: false,
  hideTimeout: 300,
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
