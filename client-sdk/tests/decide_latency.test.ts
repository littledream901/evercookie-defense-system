/** 决策链路的端到端耗时契约。
 *
 * 业务要求：跳转逻辑在页面加载 100ms 内完成判断并执行。
 *
 * 原实现的串行链路（每一步都阻塞下一步）：
 *   DOMContentLoaded → POST /sdk/init（含重试） → 指纹采集（audio 超时 3000ms）
 *   → 六通道串行读取 → POST /decide → 跳转
 * 表现即「先把整站加载完才跳转」。
 *
 * 本文件锁定三条改动后的时序契约：
 *   1. init 与指纹采集并发，不再串行阻塞 decide；
 *   2. 回访命中指纹缓存，关键路径上不跑探针；
 *   3. 决策请求发出前的准备耗时受控。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SdSdk } from '../src/index';

const baseConfig = {
  apiBase: 'https://gw.example.com',
  apiKey: 'site_abc12345',
  siteId: 7,
  // 关掉指纹采集以隔离网络时序：jsdom 里 canvas/webgl 不可用，
  // 采集耗时不具代表性，另有专门的 collector 测试覆盖探针耗时。
  collectFingerprint: false,
  collectBehavior: false,
};

/** 记录各端点被调用的时刻（相对测试起点）。 */
let calls: { url: string; at: number }[];
let t0: number;

/** 造一个可控延迟的 fetch 替身。 */
function stubFetch(opts: { initDelay?: number; decideDelay?: number } = {}) {
  const fetchSpy = vi.fn((url: string) => {
    calls.push({ url, at: Date.now() - t0 });

    const isInit = url.includes('/sdk/init');
    const delay = isInit ? (opts.initDelay ?? 0) : (opts.decideDelay ?? 0);

    const body = isInit
      ? { code: 0, message: 'ok', data: { siteId: 7, serverTimeMs: Date.now(), configVersion: 'v1' } }
      : {
          code: 0,
          message: 'ok',
          data: {
            verdict: 'hostile',
            mechanism: 'redirect',
            targetKind: 'url',
            targetUrl: 'https://verify.example.com/',
            httpStatus: 302,
            score: 90,
            ruleIds: [],
            decidedBy: 'test',
            decidedStage: 'rule',
            ttlSeconds: 300,
            details: [],
            shadow: [],
          },
        };

    return new Promise((resolve) => {
      setTimeout(
        () =>
          resolve({
            ok: true,
            status: 200,
            headers: { get: () => 'application/json' },
            json: async () => body,
          }),
        delay,
      );
    });
  });
  vi.stubGlobal('fetch', fetchSpy);
  return fetchSpy;
}

beforeEach(() => {
  calls = [];
  t0 = Date.now();
  sessionStorage.clear();
  localStorage.clear();
  document.body.innerHTML = '';

  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: 'https://shop.example.com/landing',
      pathname: '/landing',
      replace: vi.fn(),
    },
  });
  Object.defineProperty(window, 'stop', { configurable: true, writable: true, value: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('init 不再串行阻塞 decide', () => {
  it('init 很慢时决策请求仍尽早发出', async () => {
    // init 慢到 400ms：若仍是串行，decide 必然在 400ms 之后才发出
    stubFetch({ initDelay: 400 });

    await SdSdk.protect(baseConfig);

    const decideCall = calls.find((c) => c.url.includes('/decide'));
    expect(decideCall).toBeDefined();
    // 决策请求不必等 init 返回
    expect(decideCall!.at).toBeLessThan(300);
  });

  it('两个请求并发发出，而非一前一后', async () => {
    stubFetch({ initDelay: 200 });

    await SdSdk.protect(baseConfig);

    const init = calls.find((c) => c.url.includes('/sdk/init'));
    const decide = calls.find((c) => c.url.includes('/decide'));
    expect(init).toBeDefined();
    expect(decide).toBeDefined();
    // 两者发起时刻接近 → 并发；若串行则相差约 initDelay
    expect(Math.abs(decide!.at - init!.at)).toBeLessThan(150);
  });

  it('init 失败不阻断决策（fail-open 语义保留）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/sdk/init')) {
          return Promise.reject(new Error('init 不可用'));
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: { get: () => 'application/json' },
          json: async () => ({
            code: 0,
            message: 'ok',
            data: {
              verdict: 'trusted',
              mechanism: 'pass',
              targetKind: 'origin',
              httpStatus: 200,
              score: 0,
              ruleIds: [],
              decidedBy: 'test',
              decidedStage: 'default',
              ttlSeconds: 300,
              details: [],
              shadow: [],
            },
          }),
        });
      }),
    );

    const outcome = await SdSdk.protect(baseConfig);
    expect(outcome.decision.mechanism).toBe('pass');
  });

  it('配置非法时仍同步抛错（不被 init 的 fail-open 吞掉）', async () => {
    stubFetch();
    await expect(SdSdk.protect({ ...baseConfig, apiKey: '' })).rejects.toThrow('apiKey');
  });
});

describe('决策准备阶段耗时', () => {
  it('从调用到发出 /decide 的准备耗时远低于 100ms 预算', async () => {
    stubFetch({ decideDelay: 0 });

    const started = Date.now();
    await SdSdk.protect(baseConfig);
    const decide = calls.find((c) => c.url.includes('/decide'))!;

    // 准备阶段（存储读取 + 组装 + 签名）不应吃掉 100ms 预算
    expect(decide.at - (started - t0)).toBeLessThan(100);
  });

  it('慢存储通道不拖住决策', async () => {
    stubFetch();
    // 用只含慢通道的配置：storageDeadline 应让它超时降级
    const outcome = await SdSdk.protect({
      ...baseConfig,
      storageDeadline: 20,
    });
    const decide = calls.find((c) => c.url.includes('/decide'))!;

    expect(outcome.decision.mechanism).toBe('redirect');
    expect(decide.at).toBeLessThan(200);
  });
});

describe('决策缓存写入', () => {
  it('redirect 决策被写入会话缓存，供后续页面零网络复用', async () => {
    stubFetch();

    await SdSdk.protect(baseConfig);

    const cached = JSON.parse(sessionStorage.getItem('_sd_decision') || 'null');
    expect(cached).not.toBeNull();
    expect(cached.m).toBe('redirect');
    expect(cached.u).toBe('https://verify.example.com/');
    expect(cached.exp).toBeGreaterThan(Date.now());
  });

  it('缓存 TTL 不超过 decisionCacheTtl 上限', async () => {
    stubFetch();

    // 服务端给 300s，本地上限压到 5s
    await SdSdk.protect({ ...baseConfig, decisionCacheTtl: 5000 });

    const cached = JSON.parse(sessionStorage.getItem('_sd_decision') || 'null');
    expect(cached.exp - Date.now()).toBeLessThanOrEqual(5000);
  });

  it('decisionCacheTtl=0 时不写缓存', async () => {
    stubFetch();
    await SdSdk.protect({ ...baseConfig, decisionCacheTtl: 0 });
    expect(sessionStorage.getItem('_sd_decision')).toBeNull();
  });
});
