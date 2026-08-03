/** 投票与自愈引擎。 */

import { describe, expect, it, vi } from 'vitest';

import { resolveWinner, selfHeal, vote } from '../src/core/engine';
import type { StorageDriver } from '../src/storage/driver_interface';

/** 构造一个内存驱动，可控可用性与初始值。 */
function memoryDriver(
  name: string,
  initial: string | null = null,
  available = true,
): StorageDriver & { store: Map<string, string>; writes: string[] } {
  const store = new Map<string, string>();
  const writes: string[] = [];
  if (initial !== null) store.set('k', initial);
  return {
    name,
    store,
    writes,
    isAvailable: () => available,
    get: (key) => store.get(key) ?? null,
    set: (key, value) => {
      writes.push(value);
      store.set(key, value);
    },
    remove: (key) => void store.delete(key),
  };
}

describe('vote', () => {
  it('全空时无赢家', () => {
    expect(vote({ a: null, b: null })).toEqual({
      winner: null,
      confidence: 0,
      distribution: {},
      healed: false,
    });
  });

  it('多数值胜出', () => {
    const result = vote({ a: 'x', b: 'x', c: 'y' });
    expect(result.winner).toBe('x');
    expect(result.confidence).toBeCloseTo(2 / 3);
    expect(result.distribution).toEqual({ x: 2, y: 1 });
  });

  it('空串不计票', () => {
    const result = vote({ a: '', b: 'x' });
    expect(result.winner).toBe('x');
    expect(result.confidence).toBe(1);
  });

  it('平票取字典序最小，保证结果稳定', () => {
    expect(vote({ a: 'zzz', b: 'aaa' }).winner).toBe('aaa');
    // 换插入顺序结果必须相同
    expect(vote({ b: 'aaa', a: 'zzz' }).winner).toBe('aaa');
  });

  it('全一致时 healed=false', () => {
    expect(vote({ a: 'x', b: 'x' }).healed).toBe(false);
  });

  it('有通道缺值时 healed=true', () => {
    expect(vote({ a: 'x', b: null }).healed).toBe(true);
  });
});

describe('selfHeal', () => {
  it('只回写不一致的通道', () => {
    const good = memoryDriver('good', 'x');
    const stale = memoryDriver('stale', 'y');
    const empty = memoryDriver('empty');

    const healed = selfHeal(
      'k',
      'x',
      { good, stale, empty },
      { good: 'x', stale: 'y', empty: null },
    );

    expect(healed.sort()).toEqual(['empty', 'stale']);
    expect(good.writes).toEqual([]);
    expect(stale.store.get('k')).toBe('x');
    expect(empty.store.get('k')).toBe('x');
  });

  it('单通道写入抛错不影响其他通道', () => {
    const broken: StorageDriver = {
      name: 'broken',
      isAvailable: () => true,
      get: () => null,
      set: () => {
        throw new Error('quota exceeded');
      },
      remove: () => {},
    };
    const ok = memoryDriver('ok');

    const healed = selfHeal('k', 'x', { broken, ok }, { broken: null, ok: null });

    expect(healed).toEqual(['ok']);
    expect(ok.store.get('k')).toBe('x');
  });
});

describe('resolveWinner', () => {
  it('多数值胜出并自愈少数通道', async () => {
    const a = memoryDriver('a', 'v1');
    const b = memoryDriver('b', 'v1');
    const c = memoryDriver('c', 'v2');

    const outcome = await resolveWinner('k', [a, b, c]);

    expect(outcome.value).toBe('v1');
    expect(outcome.restored).toBe(true);
    expect(c.store.get('k')).toBe('v1');
  });

  it('全通道一致时不标记 restored', async () => {
    const outcome = await resolveWinner('k', [
      memoryDriver('a', 'v1'),
      memoryDriver('b', 'v1'),
    ]);

    expect(outcome.value).toBe('v1');
    expect(outcome.restored).toBe(false);
    expect(outcome.confidence).toBe(1);
  });

  it('从单一存活通道恢复身份', async () => {
    const survivor = memoryDriver('survivor', 'v1');
    const wiped1 = memoryDriver('wiped1');
    const wiped2 = memoryDriver('wiped2');

    const outcome = await resolveWinner('k', [survivor, wiped1, wiped2]);

    expect(outcome.value).toBe('v1');
    expect(outcome.restored).toBe(true);
    expect(wiped1.store.get('k')).toBe('v1');
    expect(wiped2.store.get('k')).toBe('v1');
  });

  it('不可用通道既不投票也不参与自愈统计', async () => {
    const offline = memoryDriver('offline', 'stale', false);
    const online = memoryDriver('online', 'v1');

    const outcome = await resolveWinner('k', [offline, online]);

    expect(outcome.value).toBe('v1');
    expect(outcome.restored).toBe(false);
    // 不可用通道不应被写入
    expect(offline.writes).toEqual([]);
  });

  it('全空返回 null', async () => {
    const outcome = await resolveWinner('k', [memoryDriver('a'), memoryDriver('b')]);
    expect(outcome.value).toBeNull();
    expect(outcome.restored).toBe(false);
  });

  it('isAvailable 抛错视为不可用', async () => {
    const throwing: StorageDriver = {
      name: 'throwing',
      isAvailable: () => {
        throw new Error('boom');
      },
      get: () => 'should_not_be_read',
      set: () => {},
      remove: () => {},
    };
    const ok = memoryDriver('ok', 'v1');

    const outcome = await resolveWinner('k', [throwing, ok]);
    expect(outcome.value).toBe('v1');
  });

  it('get 抛错的通道计为空值并被自愈', async () => {
    const set = vi.fn();
    const throwing: StorageDriver = {
      name: 'throwing',
      isAvailable: () => true,
      get: () => {
        throw new Error('boom');
      },
      set,
      remove: () => {},
    };

    const outcome = await resolveWinner('k', [throwing, memoryDriver('ok', 'v1')]);

    expect(outcome.value).toBe('v1');
    expect(set).toHaveBeenCalledWith('k', 'v1');
  });

  it('并行读取异步驱动', async () => {
    const slow: StorageDriver = {
      name: 'slow',
      isAvailable: async () => true,
      get: async () => {
        await new Promise((r) => setTimeout(r, 10));
        return 'v1';
      },
      set: async () => {},
      remove: async () => {},
    };

    const outcome = await resolveWinner('k', [slow, memoryDriver('fast', 'v1')]);
    expect(outcome.value).toBe('v1');
  });
});
