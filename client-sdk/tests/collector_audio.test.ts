/** Audio 探针的时序契约。
 *
 * 这是「先加载完整站再跳转」的首要成因：Chrome 的 autoplay 策略让无用户手势的
 * 页面拿到 `suspended` 的 AudioContext，`onaudioprocess` 永不触发，原实现必然
 * 走满 3000ms 超时，而指纹是 SDK 决策的必要输入（网关对 ingress=sdk 强制校验
 * 非空指纹），于是整条跳转链路被推到 3 秒之后。
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { collectAll, deriveFingerprintId } from '../src/core/collector';

const originalAudioContext = (globalThis as Record<string, unknown>).AudioContext;
const originalWebkit = (globalThis as Record<string, unknown>).webkitAudioContext;

/** 造一个指定 state 的 AudioContext 替身。 */
function stubAudioContext(state: 'suspended' | 'running', opts: { fireCallback?: boolean } = {}) {
  const close = vi.fn();
  class FakeAudioContext {
    state = state;
    destination = {};
    close = close;
    createOscillator() {
      return { type: '', connect: vi.fn(), disconnect: vi.fn(), start: vi.fn() };
    }
    createAnalyser() {
      return {
        frequencyBinCount: 32,
        connect: vi.fn(),
        disconnect: vi.fn(),
        getByteFrequencyData: (arr: Uint8Array) => arr.fill(7),
      };
    }
    createGain() {
      return { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() };
    }
    createScriptProcessor() {
      const processor: Record<string, unknown> = { connect: vi.fn(), disconnect: vi.fn() };
      if (opts.fireCallback) {
        // 模拟浏览器在 running 态异步回调
        setTimeout(() => {
          (processor.onaudioprocess as (() => void) | undefined)?.();
        }, 5);
      }
      return processor;
    }
  }
  (globalThis as Record<string, unknown>).AudioContext =
    FakeAudioContext as unknown as typeof AudioContext;
  return { close };
}

afterEach(() => {
  (globalThis as Record<string, unknown>).AudioContext = originalAudioContext;
  (globalThis as Record<string, unknown>).webkitAudioContext = originalWebkit;
  vi.useRealTimers();
});

describe('suspended AudioContext', () => {
  it('立即退出，不等满超时窗口', async () => {
    stubAudioContext('suspended');

    const started = Date.now();
    // 给一个明显大于「立即」的超时值：若实现仍在等超时，耗时会接近该值
    const data = await collectAll({ audioTimeout: 2000 });
    const elapsed = Date.now() - started;

    expect(elapsed).toBeLessThan(200);
    expect(data.audio.raw).toEqual({ error: 'audio timeout' });
  });

  it('释放 AudioContext，不泄漏', async () => {
    const { close } = stubAudioContext('suspended');
    await collectAll({ audioTimeout: 2000 });
    expect(close).toHaveBeenCalled();
  });

  it('产出与原超时载荷一致，存量访客指纹 id 不漂移', async () => {
    // 契约：suspended 提前退出只改变耗时，不改变结果。
    // 载荷一旦变化，deriveFingerprintId 的输出就变了，等于给存量访客换身份。
    stubAudioContext('suspended');
    const fast = await collectAll({ audioTimeout: 2000 });

    // 无 AudioContext 时走真超时路径的载荷
    (globalThis as Record<string, unknown>).AudioContext = class {
      state = 'running';
      destination = {};
      close() {}
      createOscillator() {
        return { type: '', connect() {}, disconnect() {}, start() {} };
      }
      createAnalyser() {
        return {
          frequencyBinCount: 32,
          connect() {},
          disconnect() {},
          getByteFrequencyData() {},
        };
      }
      createGain() {
        return { gain: { value: 1 }, connect() {}, disconnect() {} };
      }
      createScriptProcessor() {
        return { connect() {}, disconnect() {} }; // 永不回调 → 走超时
      }
    } as unknown as typeof AudioContext;
    const timedOut = await collectAll({ audioTimeout: 30 });

    expect(fast.audio.hash).toBe(timedOut.audio.hash);
    expect(deriveFingerprintId(fast)).toBe(deriveFingerprintId(timedOut));
  });
});

describe('running AudioContext', () => {
  it('正常取到频域数据，不受提前退出影响', async () => {
    stubAudioContext('running', { fireCallback: true });

    const data = await collectAll({ audioTimeout: 2000 });

    // 回调触发时取的是真实频域数据，而非超时载荷
    expect(data.audio.raw).not.toEqual({ error: 'audio timeout' });
    expect(Array.isArray(data.audio.raw)).toBe(true);
  });
});

describe('audioTimeout 默认值', () => {
  it('默认 800ms，而非原先的 3000ms', async () => {
    // 永不回调的 running context → 必然走满超时
    stubAudioContext('running', { fireCallback: false });

    const started = Date.now();
    await collectAll();
    const elapsed = Date.now() - started;

    // 只验证上界：默认值收敛到 800ms 量级，不再是 3000ms
    expect(elapsed).toBeLessThan(1500);
  });
});
