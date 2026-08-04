/** Evercookie Defense System 客户端 SDK（V2）。
 *
 * 用法：
 *   import { SdSdk } from '@fangyu/sd-sdk';
 *   const sdk = new SdSdk({ apiBase: '/api', apiKey: '...', appId: 1 });
 *   const decision = await sdk.decide();   // 自动执行处置
 *
 * 或一行接入：
 *   SdSdk.protect({ apiBase: '/api', apiKey: '...', appId: 1 });
 *
 * UMD：<script src="sd-sdk.min.js"></script> → window.SdSdk
 */

import { ENDPOINTS, defaultConfig, type SdkConfig } from './config';
import { BehaviorCollector } from './core/behavior';
import { mountChallenge, type ChallengeContext } from './core/challenge';
import { collectAll, deriveFingerprintId, type FingerprintData } from './core/collector';
import { resolveWinner } from './core/engine';
import { applyDecision, type ApplyOutcome, type ExecutorHooks } from './core/executor';
import { generateNonce, signParams } from './core/signer';
import { cacheStorageDriver } from './storage/cache_storage';
import { cookieDriver } from './storage/cookie';
import type { StorageDriver } from './storage/driver_interface';
import { indexedDBDriver } from './storage/indexed_db';
import { localStorageDriver } from './storage/local_storage';
import { sessionStorageDriver } from './storage/session_storage';
import { windowNameDriver } from './storage/window_name';
import type {
  BehaviorEvent,
  DecisionContext,
  DecisionRequestBody,
  DecisionResponse,
  SdkHeartbeatPayload,
  SdkInitPayload,
  SdkStatusPayload,
  SuccessEnvelope,
} from './types';
import { get, post, type HttpResponse } from './utils/http';

const REPEAT_KEY_META = '_sd_repeat_key';
const REPEAT_VALUE_META = '_sd_repeat_value';
const INIT_CONFIG_META = '_sd_init_config';
const DEFAULT_REPEAT_KEY = '_sd_0000';
/** 指纹 id 缓存键。回访命中后关键路径上不再跑任何探针。 */
const FINGERPRINT_META = '_sd_fp';
/**
 * 决策缓存键。刻意存在 sessionStorage 而非六通道：
 * head 同步阶段必须**同步**读到，异步通道（indexedDB/cacheStorage）在那个
 * 时点还来不及返回。
 */
const DECISION_CACHE_KEY = '_sd_decision';

/** 可缓存的机制。见 `cacheDecision` 注释说明为何排除 challenge / serve_alt。 */
const CACHEABLE_MECHANISMS = new Set<string>(['pass', 'redirect', 'deny', 'not_found']);

/** 缓存的决策快照。字段名压到单字符：sessionStorage 配额有限。 */
interface CachedDecision {
  /** mechanism */
  m: string;
  /** targetUrl */
  u: string | null;
  /** httpStatus */
  s: number;
  /** 绝对过期时间（毫秒） */
  exp: number;
}

function writeSessionCache(key: string, payload: CachedDecision): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // 隐私模式 / 配额满：缓存只是加速手段，写不进去不影响正确性
  }
}

/** 同步读决策缓存。过期或损坏均返回 null。 */
function readSessionCache(key: string): CachedDecision | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const payload = JSON.parse(raw) as Partial<CachedDecision>;
    if (typeof payload.m !== 'string' || typeof payload.exp !== 'number') return null;
    if (payload.exp <= Date.now()) {
      // 过期即清理，避免陈旧项长期占用配额
      sessionStorage.removeItem(key);
      return null;
    }
    return {
      m: payload.m,
      u: typeof payload.u === 'string' ? payload.u : null,
      s: typeof payload.s === 'number' ? payload.s : 200,
      exp: payload.exp,
    };
  } catch {
    return null;
  }
}

const DRIVER_REGISTRY: Record<string, StorageDriver> = {
  cookie: cookieDriver,
  localStorage: localStorageDriver,
  sessionStorage: sessionStorageDriver,
  indexedDB: indexedDBDriver,
  windowName: windowNameDriver,
  cacheStorage: cacheStorageDriver,
};

/** 网关不可用时的兜底处置：放行。 */
const FAIL_OPEN: DecisionResponse = {
  verdict: 'trusted',
  mechanism: 'pass',
  targetKind: 'origin',
  httpStatus: 200,
  score: 0,
  ruleIds: [],
  reason: 'gateway_unreachable',
  decidedBy: 'sdk_fail_open',
  decidedStage: 'sdk_fail_open',
  ttlSeconds: 0,
  details: [],
  shadow: [],
};

export interface DecideOptions {
  /** 要求返回各阶段详情。默认 false。 */
  requireDetails?: boolean;
  /** 覆盖全局 `autoApply`。 */
  autoApply?: boolean;
  /** 处置执行钩子。 */
  hooks?: ExecutorHooks;
}

export interface DecideOutcome {
  decision: DecisionResponse;
  /** 处置执行结果。`autoApply=false` 时为 null。 */
  applied: ApplyOutcome | null;
}

/** `SdSdk.guard()` 的返回值。 */
export interface GuardOutcome {
  /** 是否命中同会话决策缓存（命中即同步完成，未发起任何请求）。 */
  cached: boolean;
  /** 命中缓存时的处置结果；未命中为 null。 */
  applied: ApplyOutcome | null;
  /** 未命中缓存时的在途决策 Promise；命中为 null。 */
  pending: Promise<DecideOutcome> | null;
  /** SDK 实例，便于调用方后续操作（如 destroy）。 */
  sdk: SdSdk;
}

export class SdSdk {
  private config: SdkConfig;
  private initialized = false;
  /** 在途的 init Promise。用于并发去重与 `initDeadline` 竞速。 */
  private initTask: Promise<void> | null = null;
  private fingerprintCache: FingerprintData | null = null;
  private fingerprintId = '';
  private behavior: BehaviorCollector | null = null;
  private drivers: StorageDriver[] = [];
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private syncTimer: ReturnType<typeof setInterval> | null = null;
  private configVersion = '';
  /** 服务端时间 - 本地时间。用于把行为事件时间校正到服务端时钟。 */
  private clockSkewMs = 0;

  constructor(userConfig: Partial<SdkConfig> = {}) {
    this.config = { ...defaultConfig, ...userConfig };
    this.config.apiBase = normalizeApiBase(this.config.apiBase);
    this.drivers = this.config.storageTypes
      .map((type) => DRIVER_REGISTRY[type])
      .filter((d): d is StorageDriver => Boolean(d));
  }

  /** 一行接入：构造 → init → decide → 自动执行处置。 */
  static async protect(
    userConfig: Partial<SdkConfig> = {},
    options: DecideOptions = {},
  ): Promise<DecideOutcome> {
    const sdk = new SdSdk(userConfig);
    return sdk.decide(options);
  }

  /**
   * head 内同步接入：跳转判断优先于页面渲染。
   *
   * 与 `protect()` 的区别只在**时机**，规则与处置完全一致。
   *
   * 放在 `<head>` 里同步调用（脚本标签**不要**加 defer/async），此时 body 尚未
   * 解析，站点资源也还没开始下载：
   *
   * 1. 同会话已有缓存决策 → **同步**执行处置并返回，零网络、零等待。
   *    这是「立即终止后续资源加载」真正生效的路径：`window.stop()` 在解析器
   *    走到 body 之前就已调用。
   * 2. 无缓存 → 发起决策请求；`hideUntilDecided` 为 true 时先隐藏内容，
   *    判定完成或 `hideTimeout` 到点后恢复。
   *
   * 返回值：命中缓存时 `applied` 已填充且 `cached` 为 true；否则返回在途
   * Promise，调用方可自行 await（通常不需要）。
   */
  static guard(userConfig: Partial<SdkConfig> = {}, options: DecideOptions = {}): GuardOutcome {
    const sdk = new SdSdk(userConfig);
    const cached = sdk.applyCachedDecision(options);
    if (cached) {
      return { cached: true, applied: cached, pending: null, sdk };
    }

    const release = sdk.hideContent();
    const pending = sdk
      .decide(options)
      .then((outcome) => {
        release();
        return outcome;
      })
      .catch((err: unknown) => {
        // 判定失败绝不能让页面停在隐藏态
        release();
        throw err;
      });

    return { cached: false, applied: null, pending, sdk };
  }

  /** 初始化：拉取站点配置，启动行为采集与后台轮询。 */
  async init(): Promise<void> {
    if (this.initialized) return;
    this.validateConfig();

    const response = await this.postWithRetry<SuccessEnvelope<SdkInitPayload>>(
      this.url(ENDPOINTS.sdkInit),
      { appId: this.config.appId, sdkVersion: this.config.sdkVersion },
    );

    const payload = unwrap(response);
    if (payload) {
      this.configVersion = payload.configVersion ?? '';
      this.clockSkewMs = payload.serverTimeMs ? payload.serverTimeMs - Date.now() : 0;
      if (payload.sdkVersion) {
        this.config.sdkVersion = payload.sdkVersion;
      }
      // 服务端可以关停行为采集（例如站点未购买该能力）
      if (payload.collectBehavior === false) {
        this.config.collectBehavior = false;
      }
      await this.cacheInitConfig(payload);
    } else {
      // init 不可用不阻断决策：用本地缓存的配置继续，决策请求自身会再试一次
      await this.restoreInitConfig();
      this.log('init 接口不可用，使用本地缓存配置');
    }

    this.startBehavior(payload?.behavior);
    this.startTimers();
    this.initialized = true;
  }

  /** 风险决策：采集 → 签名 → POST /v2/decide → 按需执行处置。
   *
   * 时序
   * ----
   * `init()` **不再串行阻塞**本方法。它只提供 clockSkew 与行为采集策略，两者
   * 都不是决策的必要输入；串行等待等于在跳转前白加一个完整 RTT。改为与指纹
   * 采集并发，并受 `initDeadline` 约束——超时则转入后台，决策照常发出。
   *
   * 注意 `signBody` 会用到 clockSkew。init 未回来时 skew 为 0，即按本地时钟
   * 签名；网关允许 ±5 分钟偏差，与「init 失败走本地缓存」的既有降级同口径。
   */
  async decide(options: DecideOptions = {}): Promise<DecideOutcome> {
    // 配置校验必须留在此处同步抛出。init() 内部也校验，但 beginInit() 会吞掉
    // 它的异常（init 失败要 fail-open），配置写错就会变成静默不生效。
    this.validateConfig();

    // 先起 init（不 await），让它与指纹采集、存储读取并发
    const initTask = this.beginInit();

    const context = await this.buildContext();

    // 指纹采集通常比 init 的 RTT 快，此处给 init 一个收尾窗口：拿到 clockSkew
    // 能让签名与行为时间更准，但绝不为它多等。
    await this.awaitInit(initTask);

    const body = await this.signBody({
      context,
      requireDetails: options.requireDetails === true,
    });

    const response = await post<SuccessEnvelope<DecisionResponse> | DecisionResponse>(
      this.url(ENDPOINTS.decide),
      body,
      { timeout: this.config.apiTimeout, apiKey: this.config.apiKey },
    );

    const decision = extractDecision(response);
    if (!decision) {
      this.log('决策请求失败，按放行处理', response.error ?? response.status);
      return { decision: FAIL_OPEN, applied: null };
    }

    // 写决策缓存要在执行处置**之前**：redirect 分支会立刻 location.replace，
    // 之后的语句未必还有机会执行。
    this.cacheDecision(decision);

    // 持久化身份：网关认下的 repeat 值写回全部通道。
    // 不 await——写回是六通道的幂等操作，与本次处置无因果关系，await 它等于把
    // 存储写入的耗时加在跳转前面。
    if (context.repeatKey && context.repeatValue) {
      void this.persistIdentity(context.repeatKey, context.repeatValue);
    }

    const autoApply = options.autoApply ?? this.config.autoApply;
    const applied = autoApply
      ? applyDecision(decision, options.hooks ?? {}, {
          apiBase: this.config.apiBase,
          apiKey: this.config.apiKey,
          appId: this.config.appId,
          fingerprint: context.fingerprint,
          debug: this.config.debug,
        })
      : null;
    return { decision, applied };
  }

  /** 写入 Evercookie 值到全部可用通道，带重试。 */
  async set(key: string, value: string): Promise<void> {
    await Promise.all(
      this.drivers.map(async (driver) => {
        for (let attempt = 0; attempt < this.config.retryCount; attempt++) {
          try {
            await driver.set(key, value);
            return;
          } catch {
            if (attempt < this.config.retryCount - 1) {
              await sleep(this.config.retryDelay);
            }
          }
        }
      }),
    );
  }

  /** 读取 Evercookie 值：全通道投票 + 自愈。 */
  async get(key: string): Promise<string | null> {
    const outcome = await resolveWinner(key, this.drivers);
    return outcome.value;
  }

  /** 采集指纹（带缓存）。 */
  async collectFingerprint(): Promise<FingerprintData> {
    if (this.fingerprintCache) return this.fingerprintCache;
    const data = await collectAll({
      thirdPartyProbe: this.config.thirdPartyProbe,
      audioTimeout: this.config.audioTimeout,
    });
    this.fingerprintCache = data;
    this.fingerprintId = deriveFingerprintId(data);
    void this.cacheFingerprintId(this.fingerprintId);
    return data;
  }

  /** 手动上报缓冲中的行为事件。 */
  async flushBehavior(): Promise<number> {
    const events = this.behavior?.drain() ?? [];
    if (!events.length) return 0;

    const response = await post<SuccessEnvelope<SdkHeartbeatPayload>>(
      this.url(ENDPOINTS.sdkHeartbeat),
      await this.signBody({
        appId: this.config.appId,
        fingerprint: this.fingerprintId,
        sdkVersion: this.config.sdkVersion,
        behaviorEvents: this.alignEventTimes(events),
      }),
      { timeout: this.config.apiTimeout, apiKey: this.config.apiKey },
    );

    const payload = unwrap(response);
    if (!payload) {
      // 上报失败：事件已从缓冲取出，此处不回滚——重放旧事件会污染时序库，
      // 且后续事件会持续产生，丢弃一批的代价小于乱序入库。
      this.log('行为上报失败');
      return 0;
    }
    this.configVersion = payload.configVersion ?? this.configVersion;
    return payload.accepted ?? 0;
  }

  getConfig(): Readonly<SdkConfig> {
    return { ...this.config, apiKey: this.config.apiKey ? '***' : '', appSecret: '' };
  }

  destroy(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    if (this.syncTimer) clearInterval(this.syncTimer);
    this.heartbeatTimer = null;
    this.syncTimer = null;
    this.behavior?.destroy();
    this.behavior = null;
    this.initialized = false;
    this.initTask = null;
  }

  // ── 内部 ──

  private url(path: string): string {
    return `${this.config.apiBase}${path}`;
  }

  private validateConfig(): void {
    if (!this.config.apiBase) {
      throw new Error('apiBase 不能为空，请显式传入 Gateway API 基址');
    }
    if (!this.config.apiKey) {
      throw new Error('apiKey 不能为空');
    }
    if (!Number.isInteger(this.config.appId) || this.config.appId <= 0) {
      throw new Error('appId 必须是正整数');
    }
  }

  private async ensureInit(): Promise<void> {
    if (!this.initialized) await this.init();
  }

  /** 启动 init（幂等，不等待）。返回同一个在途 Promise，避免并发重复请求。 */
  private beginInit(): Promise<void> {
    if (this.initialized) return Promise.resolve();
    if (!this.initTask) {
      // catch 挂在此处：init 失败不能变成未处理的 rejection，也不该冒泡到
      // decide()——init 不可用时决策仍应照常发出（既有 fail-open 语义）。
      this.initTask = this.init().catch((err) => {
        this.log('init 失败', err);
      });
    }
    return this.initTask;
  }

  /** 在 `initDeadline` 内等 init 收尾；超时则让它转入后台。 */
  private async awaitInit(task: Promise<void>): Promise<void> {
    const deadline = this.config.initDeadline;
    if (deadline <= 0) return;

    let timer: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([
      task,
      new Promise<void>((resolve) => {
        timer = setTimeout(resolve, deadline);
      }),
    ]);
    if (timer) clearTimeout(timer);
  }

  /** 组装决策上下文。
   *
   * 关键路径优化
   * ------------
   * 三处原本都是串行阻塞，合计能吃掉几百毫秒：
   * 1. 指纹采集 → 回访直接读缓存（`resolveFingerprintId`）；
   * 2. `repeatKey` 与主值读取 → 由串行两次 `resolveWinner` 改为并发，
   *    并施加 `storageDeadline`；
   * 3. 慢通道超时后转后台自愈，不阻塞本次决策。
   */
  private async buildContext(): Promise<DecisionContext> {
    const deadlineMs = this.config.storageDeadline;

    // 指纹与存储读取并发：两者互不依赖
    const [, repeatKeyRaw] = await Promise.all([
      this.config.collectFingerprint && !this.fingerprintId
        ? this.resolveFingerprintId()
        : Promise.resolve(),
      resolveWinner(REPEAT_KEY_META, this.drivers, { deadlineMs }),
    ]);

    const repeatKey = repeatKeyRaw.value || DEFAULT_REPEAT_KEY;
    const stored = await resolveWinner(repeatKey, this.drivers, { deadlineMs });
    const repeatValue =
      stored.value ?? (await resolveWinner(REPEAT_VALUE_META, this.drivers, { deadlineMs })).value;

    const events = this.behavior?.drain() ?? [];

    return {
      appId: this.config.appId,
      ingress: 'sdk',
      // 指纹为空时网关会拒（ingress=sdk 强制要求）。关闭采集就必须自己给值，
      // 这里退化到 repeat 值派生，保证请求仍然合法。
      fingerprint: this.fingerprintId || (repeatValue ? `repeat:${repeatValue}` : ''),
      userAgent: navigator.userAgent,
      // ip 刻意不发：浏览器不知道自己的出口 IP，由网关从 socket 填充
      referer: document.referrer || null,
      visitUrl: location.href,
      path: location.pathname,
      method: 'GET',
      clientLanguage: navigator.language || null,
      repeatKey,
      repeatValue: repeatValue ?? null,
      evercookieRestored: stored.restored,
      behaviorEvents: this.alignEventTimes(events),
      // Hybrid 双层：适配器把第一层结论存在 Redis，SDK 靠这个 token 让网关取回。
      // 不带时网关的 HYBRID_LOOKUP 直接返回 None，两层退化为互不相干的独立判定。
      ...(this.config.serverToken ? { extra: { serverToken: this.config.serverToken } } : {}),
    };
  }

  /**
   * 取指纹 id：优先读本地缓存，未命中才跑完整探针。
   *
   * 网关对 `ingress=sdk` 强制要求非空指纹（见 `decision.py` 的
   * `_resolve_fingerprint`），因此这一步无法跳过，只能避免重复付出代价。
   * 首访必须跑一次探针；回访读缓存，关键路径上的 canvas / webgl / audio
   * 开销全部归零。
   *
   * 缓存只存**派生后的 id**，不存原始指纹分量：id 是 `deriveFingerprintId`
   * 的输出，与实时采集结果逐字节一致，不会让上报值失真。
   */
  private async resolveFingerprintId(): Promise<void> {
    if (this.config.fingerprintCacheTtl > 0) {
      const cached = await this.readFingerprintCache();
      if (cached) {
        this.fingerprintId = cached;
        // 后台补齐完整指纹数据：心跳与后续请求需要，但不占用本次关键路径。
        void this.collectFingerprint();
        return;
      }
    }
    await this.collectFingerprint();
  }

  /** 读指纹缓存。TTL 过期或格式损坏均视为未命中。 */
  private async readFingerprintCache(): Promise<string | null> {
    const raw = await resolveWinner(FINGERPRINT_META, this.drivers, {
      deadlineMs: this.config.storageDeadline,
    });
    if (!raw.value) return null;
    try {
      const payload = JSON.parse(raw.value) as { id?: unknown; at?: unknown };
      const id = typeof payload.id === 'string' ? payload.id : '';
      const at = Number(payload.at ?? 0);
      if (!id || !at) return null;
      // 时钟回拨（at 在未来）同样视为失效，避免缓存永不过期
      const age = Date.now() - at;
      if (age < 0 || age > this.config.fingerprintCacheTtl) return null;
      return id;
    } catch {
      return null;
    }
  }

  private async cacheFingerprintId(id: string): Promise<void> {
    if (this.config.fingerprintCacheTtl <= 0 || !id) return;
    await this.set(FINGERPRINT_META, JSON.stringify({ id, at: Date.now() }));
  }

  /**
   * 缓存本次决策，供同会话后续页面在 head 同步阶段零网络复用。
   *
   * 只缓存**确定性处置**（redirect / deny / not_found / pass）：
   * - `challenge` 不缓存：挑战 token 一次性消费，复用必然失败；
   * - `serve_alt` 不缓存：`pageContent` 可能很大，且随页面而异。
   *
   * TTL 取 `min(服务端 ttlSeconds, decisionCacheTtl)`，服务端说了算，本地只
   * 设上限——避免服务端给出超长 TTL 时规则更新迟迟不生效。
   */
  private cacheDecision(decision: DecisionResponse): void {
    if (this.config.decisionCacheTtl <= 0) return;
    if (!CACHEABLE_MECHANISMS.has(decision.mechanism)) return;

    const serverTtl = (decision.ttlSeconds ?? 0) * 1000;
    // 服务端 ttlSeconds 为 0 表示「不要缓存」，直接跳过
    if (serverTtl <= 0) return;

    writeSessionCache(DECISION_CACHE_KEY, {
      m: decision.mechanism,
      u: decision.targetUrl ?? null,
      s: decision.httpStatus,
      exp: Date.now() + Math.min(serverTtl, this.config.decisionCacheTtl),
    });
  }

  /**
   * 同步读缓存并执行处置。命中返回处置结果，未命中返回 null。
   *
   * 全程同步，可在 head 阶段调用。`pass` 命中时不做任何干预，直接返回
   * `action:'none'`，让页面正常渲染——这保证了正常访客不会被这条路径影响。
   */
  private applyCachedDecision(options: DecideOptions = {}): ApplyOutcome | null {
    if (this.config.decisionCacheTtl <= 0) return null;

    const cached = readSessionCache(DECISION_CACHE_KEY);
    if (!cached) return null;

    const decision: DecisionResponse = {
      ...FAIL_OPEN,
      verdict: cached.m === 'pass' ? 'trusted' : 'hostile',
      mechanism: cached.m as DecisionResponse['mechanism'],
      targetKind: cached.u ? 'url' : 'origin',
      targetUrl: cached.u,
      httpStatus: cached.s,
      reason: 'sdk_decision_cache',
      decidedBy: 'sdk_cache',
      decidedStage: 'sdk_cache',
    };

    const autoApply = options.autoApply ?? this.config.autoApply;
    if (!autoApply) return null;

    return applyDecision(decision, options.hooks ?? {}, {
      apiBase: this.config.apiBase,
      apiKey: this.config.apiKey,
      appId: this.config.appId,
      fingerprint: this.fingerprintId,
      debug: this.config.debug,
    });
  }

  /**
   * 判定完成前隐藏内容，返回恢复函数。
   *
   * `hideUntilDecided` 默认关闭——这条路径会短暂影响正常访客的渲染，只有明确
   * 需要「Bot 不得在判定前看到内容」的页面才该开启。
   *
   * 用注入 `<style>` 而非改 `body.style`：head 阶段 body 还不存在。
   * `hideTimeout` 兜底强制显示，避免网络异常时白屏。
   */
  private hideContent(): () => void {
    if (!this.config.hideUntilDecided || typeof document === 'undefined') {
      return () => {};
    }

    let style: HTMLStyleElement | null = null;
    try {
      style = document.createElement('style');
      style.setAttribute('data-sd-hide', '1');
      // 用 visibility 而非 display：不触发重排，恢复后无布局跳动
      style.textContent = 'body{visibility:hidden!important}';
      document.head?.appendChild(style);
    } catch {
      return () => {};
    }

    let done = false;
    // timer 先声明后赋值：release 可能在 setTimeout 返回前被调用
    let timer: ReturnType<typeof setTimeout> | undefined;
    const release = () => {
      if (done) return;
      done = true;
      if (timer !== undefined) clearTimeout(timer);
      try {
        style?.remove();
      } catch {
        // ignore
      }
    };
    timer = setTimeout(release, this.config.hideTimeout);
    return release;
  }

  /**
   * 把事件时间校正到服务端时钟。
   *
   * 网关会把偏移超过 ±5 分钟的时间戳整条替换为服务端时间（见
   * `normalize_event_time`），那样会丢掉事件之间的相对顺序。客户端先按
   * init 拿到的 skew 校正，能让时钟不准的设备也保住时序。
   */
  private alignEventTimes(events: BehaviorEvent[]): BehaviorEvent[] {
    if (!this.clockSkewMs) return events;
    return events.map((e) => ({ ...e, clientTsMs: e.clientTsMs + this.clockSkewMs }));
  }

  /** 附加签名字段。未配置 appSecret 时原样返回（站点未开启验签）。 */
  private async signBody<T extends Record<string, unknown>>(body: T): Promise<T> {
    if (!this.config.appSecret) return body;

    const signable: Record<string, unknown> = {
      ...body,
      timestamp: Math.floor((Date.now() + this.clockSkewMs) / 1000),
      nonce: generateNonce(),
    };
    signable.sign = await signParams(signable, this.config.appSecret);
    return signable as unknown as T;
  }

  private async persistIdentity(repeatKey: string, repeatValue: string): Promise<void> {
    await Promise.all([
      this.set(REPEAT_KEY_META, repeatKey),
      this.set(REPEAT_VALUE_META, repeatValue),
      this.set(repeatKey, repeatValue),
    ]);
  }

  private async cacheInitConfig(payload: SdkInitPayload): Promise<void> {
    await this.set(
      INIT_CONFIG_META,
      JSON.stringify({
        appId: payload.appId ?? this.config.appId,
        sdkVersion: payload.sdkVersion ?? this.config.sdkVersion,
        configVersion: payload.configVersion ?? '',
        collectBehavior: payload.collectBehavior !== false,
        cachedAt: Date.now(),
      }),
    );
  }

  private async restoreInitConfig(): Promise<void> {
    const cached = await this.get(INIT_CONFIG_META);
    if (!cached) return;
    try {
      const payload = JSON.parse(cached) as Record<string, unknown>;
      const cachedAt = Number(payload.cachedAt ?? 0);
      if (cachedAt && Date.now() - cachedAt > this.config.initCacheTtl) return;
      if (typeof payload.sdkVersion === 'string') {
        this.config.sdkVersion = payload.sdkVersion;
      }
      if (typeof payload.configVersion === 'string') {
        this.configVersion = payload.configVersion;
      }
      if (payload.collectBehavior === false) {
        this.config.collectBehavior = false;
      }
    } catch {
      // 缓存损坏，忽略
    }
  }

  private startBehavior(policy?: SdkInitPayload['behavior']): void {
    if (!this.config.collectBehavior || this.behavior) return;
    if (policy && policy.enabled === false) return;

    this.behavior = new BehaviorCollector({
      enabled: true,
      ...(policy?.intervalMs ? { sampleIntervalMs: policy.intervalMs } : {}),
      ...(policy?.maxEvents ? { maxEvents: policy.maxEvents } : {}),
    });
    this.behavior.start();
  }

  private startTimers(): void {
    if (typeof window === 'undefined') return;

    if (!this.heartbeatTimer && this.config.heartbeatInterval > 0) {
      this.heartbeatTimer = setInterval(() => {
        void this.flushBehavior();
      }, this.config.heartbeatInterval);
    }

    if (!this.syncTimer && this.config.syncInterval > 0) {
      this.syncTimer = setInterval(() => {
        void this.syncConfigVersion();
      }, this.config.syncInterval);
    }
  }

  private async syncConfigVersion(): Promise<void> {
    const response = await get<SuccessEnvelope<SdkStatusPayload>>(
      `${this.url(ENDPOINTS.sdkStatus)}?appId=${encodeURIComponent(String(this.config.appId))}`,
      { timeout: this.config.apiTimeout, apiKey: this.config.apiKey },
    );
    const payload = unwrap(response);
    if (!payload) return;

    if (payload.serverTimeMs) {
      this.clockSkewMs = payload.serverTimeMs - Date.now();
    }
    // 配置版本变了：清掉 init 标记，下次 decide 会重新拉配置
    if (payload.configVersion && payload.configVersion !== this.configVersion) {
      this.configVersion = payload.configVersion;
      this.initialized = false;
      // 同时清掉在途任务句柄，否则 beginInit() 会复用已完成的旧 Promise，
      // 重新初始化永远不会真正发生。
      this.initTask = null;
      this.log('检测到配置更新，下次决策前将重新初始化');
    }
  }

  private async postWithRetry<T>(url: string, data: object): Promise<HttpResponse<T>> {
    let last: HttpResponse<T> = { ok: false, data: null, status: 0, error: '未发起请求' };
    for (let attempt = 0; attempt < this.config.retryCount; attempt++) {
      last = await post<T>(url, data, {
        timeout: this.config.apiTimeout,
        apiKey: this.config.apiKey,
      });
      if (last.ok) return last;
      // 4xx 是请求本身的问题，重试只是白等
      if (last.status >= 400 && last.status < 500) return last;
      if (attempt < this.config.retryCount - 1) {
        await sleep(this.config.retryDelay * (attempt + 1));
      }
    }
    return last;
  }

  private log(...args: unknown[]): void {
    if (this.config.debug) {
      console.log('[SdSdk]', ...args);
    }
  }
}

/** 去掉尾部斜杠与重复的 `/v2`，避免拼出 `/v2/v2/decide`。 */
function normalizeApiBase(base: string): string {
  return base.replace(/\/+$/, '').replace(/\/v2$/, '');
}

/** 解包 `SuccessResponse` 包装。网关统一包一层 `{code,message,data}`。 */
function unwrap<T>(response: HttpResponse<SuccessEnvelope<T>>): T | null {
  if (!response.ok || !response.data) return null;
  const body = response.data as SuccessEnvelope<T> & Partial<T>;
  if (body.data !== undefined && body.data !== null) return body.data;
  return null;
}

/** 决策响应既可能带包装（/decide）也可能裸返（/decide/fast）。 */
function extractDecision(
  response: HttpResponse<SuccessEnvelope<DecisionResponse> | DecisionResponse>,
): DecisionResponse | null {
  if (!response.ok || !response.data) return null;
  const body = response.data as Partial<SuccessEnvelope<DecisionResponse>> &
    Partial<DecisionResponse>;
  if (body.data && typeof body.data === 'object') return body.data;
  if (typeof body.mechanism === 'string') return body as DecisionResponse;
  return null;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

if (typeof window !== 'undefined') {
  (window as unknown as { SdSdk: typeof SdSdk }).SdSdk = SdSdk;
}

export { applyDecision } from './core/executor';
export type { ExecutorContext } from './core/executor';
export { mountChallenge } from './core/challenge';
export type { ChallengeContext, ChallengeOptions } from './core/challenge';
export { BehaviorCollector } from './core/behavior';
export { buildSignPayload, generateNonce, signParams } from './core/signer';
export { canonicalJson, djb2Hash, hmacSha256, sha256 } from './utils/crypto';
export { collectAll, deriveFingerprintId } from './core/collector';
export { resolveWinner, selfHeal, vote } from './core/engine';
export { ENDPOINTS, defaultConfig } from './config';
export type { SdkConfig } from './config';
export type { ResolveOptions } from './core/engine';
export type { FingerprintData, FingerprintItem } from './core/collector';
export type { ResolveOutcome, VoteResult } from './core/engine';
export type { ApplyOutcome, ExecutorHooks } from './core/executor';
export type { BehaviorConfig } from './core/behavior';
export type { StorageDriver } from './storage/driver_interface';
export type * from './types';

// ──────────────────────────────────────────────────────────────────────────────
// WordPress 自动挂载（FY-DISP-004）
// ──────────────────────────────────────────────────────────────────────────────

/**
 * WordPress 挑战页自动认领：页面加载后检查 #fangyu-challenge 挂载点，
 * 读取 data 属性（token、app-id、api-key、gateway、kind），自动渲染挑战界面。
 *
 * 仅在 DOM 中存在该元素且未被 data-claimed 标记时执行，避免重复初始化。
 */
function autoMountWordPressChallenge(): void {
  if (typeof document === 'undefined') return;

  const el = document.getElementById('fangyu-challenge');
  if (!el || el.dataset.claimed) return;

  const token = el.dataset.token;
  const appId = el.dataset.appId;
  const apiKey = el.dataset.apiKey;
  const gateway = el.dataset.gateway;
  const kind = el.dataset.kind as 'captcha' | 'js' | undefined;
  const returnUrl = el.dataset.return;

  if (!token || !appId || !apiKey || !gateway) {
    console.warn('[fangyu] #fangyu-challenge 数据属性不完整，跳过自动挂载', {
      token: !!token,
      appId: !!appId,
      apiKey: !!apiKey,
      gateway: !!gateway,
    });
    return;
  }

  el.dataset.claimed = '1';

  // 构造 DecisionResponse 结构（仅挑战相关字段有意义）
  const decision = {
    verdict: 'hostile',
    mechanism: 'challenge',
    challengeKind: kind || 'captcha',
    challengeToken: token,
    httpStatus: 403,
    targetKind: null,
    targetUrl: null,
    score: 0,
    ruleIds: [],
    reason: 'wordpress_challenge_page',
    decidedBy: 'wordpress_adapter',
    decidedStage: 'wordpress_adapter',
    ttlSeconds: 0,
    details: [],
    shadow: [],
  } as unknown as DecisionResponse;

  const context: ChallengeContext = {
    apiBase: normalizeApiBase(gateway),
    apiKey,
    appId: parseInt(appId, 10),
    // 必须与服务端 decide 时所用值一致，否则 token 校验的指纹比对会失败
    fingerprint: el.dataset.fingerprint || '',
    debug: false,
  };

  mountChallenge(
    decision,
    context,
    {
      onSuccess: () => {
        if (returnUrl) {
          window.location.href = returnUrl;
        } else {
          window.location.reload();
        }
      },
      onError: (msg: string) => {
        console.error('[fangyu] 挑战失败:', msg);
        el.innerHTML = `<p style="color:#f5222d;margin-top:16px">验证失败：${msg}</p>`;
      },
    },
    el,
  );
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoMountWordPressChallenge);
  } else {
    autoMountWordPressChallenge();
  }
}
