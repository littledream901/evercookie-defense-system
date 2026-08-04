/** head 同步接入：跳转判断优先于页面渲染。
 *
 * 性能要求：跳转逻辑必须在页面加载 100ms 内完成判断并执行。
 * 命中同会话决策缓存时该路径是**纯同步、零网络**的，因此可在 `<head>` 内、
 * body 尚未解析时就完成跳转——这是「不先加载整站再跳转」的关键。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SdSdk } from '../src/index';

const CACHE_KEY = '_sd_decision';

let replace: ReturnType<typeof vi.fn>;
let stop: ReturnType<typeof vi.fn>;

const baseConfig = {
  apiBase: 'https://gw.example.com',
  apiKey: 'site_abc12345',
  appId: 7,
};

beforeEach(() => {
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  sessionStorage.clear();

  replace = vi.fn();
  stop = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      href: 'https://shop.example.com/landing',
      pathname: '/landing',
      replace,
    },
  });
  Object.defineProperty(window, 'stop', { configurable: true, writable: true, value: stop });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** 写入一条有效的决策缓存。 */
function seedCache(payload: Record<string, unknown>) {
  sessionStorage.setItem(CACHE_KEY, JSON.stringify(payload));
}

describe('命中缓存：同步零网络跳转', () => {
  it('缓存 redirect 时立即跳转，不发任何请求', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    const outcome = SdSdk.guard(baseConfig);

    expect(outcome.cached).toBe(true);
    expect(outcome.applied?.action).toBe('redirect');
    expect(replace).toHaveBeenCalledWith('https://verify.example.com/');
    // 零网络：这是能压进 100ms 的根本原因
    expect(fetchSpy).not.toHaveBeenCalled();
    // 未发起在途决策
    expect(outcome.pending).toBeNull();
  });

  it('同步完成——返回前跳转已执行，无需 await', () => {
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    // guard() 返回时（尚未 await 任何东西）跳转就已发生
    SdSdk.guard(baseConfig);
    expect(replace).toHaveBeenCalled();
  });

  it('跳转前先中止在途资源加载', () => {
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });
    SdSdk.guard(baseConfig);
    expect(stop).toHaveBeenCalled();
    expect(stop.mock.invocationCallOrder[0]).toBeLessThan(replace.mock.invocationCallOrder[0]);
  });

  it('耗时远低于 100ms 预算', () => {
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    const started = performance.now();
    SdSdk.guard(baseConfig);
    const elapsed = performance.now() - started;

    expect(replace).toHaveBeenCalled();
    expect(elapsed).toBeLessThan(100);
  });

  it('缓存 deny 时渲染阻断遮罩', () => {
    seedCache({ m: 'deny', u: null, s: 403, exp: Date.now() + 60_000 });

    const outcome = SdSdk.guard(baseConfig);

    expect(outcome.applied?.action).toBe('block');
    expect(document.querySelector('[data-sd-overlay]')).not.toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});

describe('缓存 pass：不影响正常渲染', () => {
  it('不跳转、不中止加载、不遮罩', () => {
    seedCache({ m: 'pass', u: null, s: 200, exp: Date.now() + 60_000 });

    const outcome = SdSdk.guard(baseConfig);

    expect(outcome.cached).toBe(true);
    expect(outcome.applied?.action).toBe('none');
    expect(replace).not.toHaveBeenCalled();
    // 正常访客的页面加载绝不能被打断
    expect(stop).not.toHaveBeenCalled();
    expect(document.querySelector('[data-sd-overlay]')).toBeNull();
  });
});

describe('缓存失效', () => {
  it('过期缓存不生效，转为发起决策', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() - 1 });

    const outcome = SdSdk.guard(baseConfig);

    expect(outcome.cached).toBe(false);
    expect(replace).not.toHaveBeenCalled();
    expect(outcome.pending).not.toBeNull();
    // 过期项被清理
    expect(sessionStorage.getItem(CACHE_KEY)).toBeNull();
  });

  it('损坏的缓存不生效且不抛错', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    sessionStorage.setItem(CACHE_KEY, '{ not json');

    expect(() => SdSdk.guard(baseConfig)).not.toThrow();
    expect(replace).not.toHaveBeenCalled();
  });

  it('无缓存时返回在途 Promise', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    const outcome = SdSdk.guard(baseConfig);

    expect(outcome.cached).toBe(false);
    expect(outcome.pending).toBeInstanceOf(Promise);
  });
});

describe('hideUntilDecided', () => {
  it('默认关闭——不注入隐藏样式，正常渲染流程不受影响', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    SdSdk.guard(baseConfig);

    expect(document.querySelector('[data-sd-hide]')).toBeNull();
  });

  it('开启后注入隐藏样式', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    SdSdk.guard({ ...baseConfig, hideUntilDecided: true });

    const style = document.querySelector('[data-sd-hide]');
    expect(style).not.toBeNull();
    expect(style?.textContent).toContain('visibility:hidden');
  });

  it('hideTimeout 到点后强制显示，避免白屏', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    SdSdk.guard({ ...baseConfig, hideUntilDecided: true, hideTimeout: 20 });
    expect(document.querySelector('[data-sd-hide]')).not.toBeNull();

    await new Promise((r) => setTimeout(r, 80));

    expect(document.querySelector('[data-sd-hide]')).toBeNull();
  });

  it('命中缓存时不注入隐藏样式（无需等待）', () => {
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    SdSdk.guard({ ...baseConfig, hideUntilDecided: true });

    expect(document.querySelector('[data-sd-hide]')).toBeNull();
  });
});

describe('autoApply=false', () => {
  it('不自动执行缓存处置，交由调用方决定', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    const outcome = SdSdk.guard({ ...baseConfig, autoApply: false });

    expect(replace).not.toHaveBeenCalled();
    expect(outcome.cached).toBe(false);
  });
});

describe('decisionCacheTtl=0', () => {
  it('禁用缓存时忽略已有缓存项', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    seedCache({ m: 'redirect', u: 'https://verify.example.com/', s: 302, exp: Date.now() + 60_000 });

    const outcome = SdSdk.guard({ ...baseConfig, decisionCacheTtl: 0 });

    expect(outcome.cached).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });
});
