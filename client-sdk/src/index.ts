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

export class SdSdk {
  private config: SdkConfig;
  private initialized = false;
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

  /** 风险决策：采集 → 签名 → POST /v2/decide → 按需执行处置。 */
  async decide(options: DecideOptions = {}): Promise<DecideOutcome> {
    await this.ensureInit();

    const context = await this.buildContext();
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

    // 持久化身份：网关认下的 repeat 值写回全部通道
    if (context.repeatKey && context.repeatValue) {
      await this.persistIdentity(context.repeatKey, context.repeatValue);
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
    const data = await collectAll({ thirdPartyProbe: this.config.thirdPartyProbe });
    this.fingerprintCache = data;
    this.fingerprintId = deriveFingerprintId(data);
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

  /** 组装决策上下文。 */
  private async buildContext(): Promise<DecisionContext> {
    if (this.config.collectFingerprint && !this.fingerprintId) {
      await this.collectFingerprint();
    }

    const repeatKey = (await this.get(REPEAT_KEY_META)) || DEFAULT_REPEAT_KEY;
    const stored = await resolveWinner(repeatKey, this.drivers);
    const repeatValue = stored.value ?? (await this.get(REPEAT_VALUE_META));

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
    };
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
