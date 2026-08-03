/** V2 wire 契约的 TypeScript 镜像。
 *
 * 字段名与 `fangyu_shared.schemas.decision` / `.disposition` / `.clock` 的
 * camelCase alias 逐一对应。**改这里必须同步改 Python 侧**，否则请求会被
 * pydantic 静默丢字段（BaseSchema 用默认的 extra="ignore"）。
 */

/** 裁决：为什么。对应 Python `Verdict`。 */
export type Verdict = 'trusted' | 'suspect' | 'hostile';

/** 机制：怎么做。对应 Python `Mechanism`。 */
export type Mechanism =
  | 'pass'
  | 'serve_alt'
  | 'redirect'
  | 'challenge'
  | 'deny'
  | 'not_found';

/** 目标类型：去哪。对应 Python `TargetKind`。 */
export type TargetKind = 'origin' | 'url' | 'page_resource' | 'status_only';

/** 挑战类型，仅 mechanism='challenge' 时有意义。 */
export type ChallengeKind = 'captcha' | 'js';

/** 接入来源。浏览器 SDK 恒为 'sdk'。 */
export type IngressKind = 'sdk' | 'adapter';

/** 行为事件类型。对应 Python `BehaviorKind`，枚举外的值会被网关拒绝。 */
export type BehaviorKind =
  | 'page_view'
  | 'click'
  | 'mouse_move'
  | 'scroll'
  | 'key_press'
  | 'focus'
  | 'blur'
  | 'submit';

/**
 * 行为事件 data 的取值范围。
 *
 * 刻意限制为整数而非任意 number：Python 侧待签串把 dict 序列化成
 * `json.dumps(sort_keys=True, separators=(",",":"))`，浮点数在两语言的
 * 字符串化上不一致（Python `1.0` → `"1.0"`，JS `1.0` → `"1"`），
 * 会导致验签失败。坐标、时长等一律取整。
 */
export type BehaviorScalar = number | string | boolean;

/** 单条行为事件。对应 Python `BehaviorEvent`。 */
export interface BehaviorEvent {
  kind: BehaviorKind;
  /** 客户端事件时间（毫秒）。网关会夹取到服务端时间 ±5 分钟内。 */
  clientTsMs: number;
  data: Record<string, BehaviorScalar>;
}

/** 决策上下文。对应 Python `DecisionContext`。 */
export interface DecisionContext {
  appId: number;
  ingress: IngressKind;
  fingerprint: string;
  fingerprintIsDerived?: boolean;
  deviceId?: string | null;
  /**
   * 浏览器无法得知自己的出口 IP，SDK 路径**不发送**该字段，
   * 由网关从 socket peer 填充（见 `v2/decide.py` 的 `_resolve_ip`）。
   */
  ip?: string | null;
  userAgent: string;
  referer?: string | null;
  visitUrl?: string | null;
  path?: string;
  method?: string;
  sessionId?: string | null;
  clientLanguage?: string | null;
  repeatKey?: string | null;
  repeatValue?: string | null;
  evercookieRestored?: boolean;
  behaviorEvents?: BehaviorEvent[];
  extra?: Record<string, unknown>;
}

/** /v2/decide 请求体。签名字段与 context 同级——中间件读顶层参数。 */
export interface DecisionRequestBody {
  context: DecisionContext;
  requireDetails?: boolean;
  /** 秒级 Unix 时间戳，参与签名。 */
  timestamp?: number;
  /** 一次性随机串，参与签名。 */
  nonce?: string;
  /** HMAC-SHA256(app_secret, 待签串)。 */
  sign?: string;
}

export interface DecisionDetail {
  stage: string;
  ruleId?: number | null;
  score?: number | null;
  reason?: string | null;
}

export interface ShadowOutcome {
  ruleId?: number | null;
  ruleName: string;
  verdict: Verdict;
  mechanism: Mechanism;
}

/** /v2/decide 响应。对应 Python `DecisionResponse`。 */
export interface DecisionResponse {
  verdict: Verdict;
  mechanism: Mechanism;
  targetKind: TargetKind;
  targetUrl?: string | null;
  httpStatus: number;
  challengeKind?: ChallengeKind | null;
  challengeToken?: string | null;
  score: number;
  ruleIds: number[];
  reason?: string | null;
  decidedBy: string;
  decidedStage: string;
  ttlSeconds: number;
  details: DecisionDetail[];
  shadow: ShadowOutcome[];
  requestId?: string | null;
  /** serve_alt 命中时的页面内容，客户端直接渲染。 */
  pageContent?: string | null;
}

/** 网关统一响应包装。对应 Python `SuccessResponse[T]`。 */
export interface SuccessEnvelope<T> {
  code: number;
  message: string;
  data: T;
  request_id?: string | null;
}

/** /v2/sdk/init 响应载荷。 */
export interface SdkInitPayload {
  appId: number;
  sdkVersion: string;
  /** 服务端当前毫秒时间，用于校正客户端时钟偏移。 */
  serverTimeMs: number;
  configVersion: string;
  behavior: SdkBehaviorPolicy;
  /** 站点是否启用行为采集。关闭时 SDK 不绑定任何事件监听。 */
  collectBehavior: boolean;
}

/** 服务端下发的行为采集策略。 */
export interface SdkBehaviorPolicy {
  enabled: boolean;
  /** 批量上报间隔（毫秒）。 */
  intervalMs: number;
  /** 单次请求携带的事件上限，与网关 `MAX_BEHAVIOR_EVENTS_PER_REQUEST` 对齐。 */
  maxEvents: number;
}

/** /v2/sdk/status 响应载荷。 */
export interface SdkStatusPayload {
  appId: number;
  configVersion: string;
  serverTimeMs: number;
}

/** /v2/sdk/heartbeat 响应载荷。 */
export interface SdkHeartbeatPayload {
  accepted: number;
  serverTimeMs: number;
  configVersion: string;
}
