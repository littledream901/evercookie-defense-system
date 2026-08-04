/** 存储读取的软上限：慢通道不得拖住决策，但自愈语义必须保留。
 *
 * indexedDB / cacheStorage 是异步通道，隐私模式或磁盘繁忙时可能显著变慢。
 * 决策链路要把跳转判断压进 100ms，不能被单通道阻塞；但 Evercookie 的核心价值
 * 正是「清掉部分通道仍能恢复身份」，所以超时只能降级为**延后自愈**，不能是
 * 放弃自愈。
 */

import { describe, expect, it, vi } from 'vitest';

import { resolveWinner } from '../src/core/engine';
import type { StorageDriver } from '../src/storage/driver_interface';

function syncDriver(name: string, value: string | null): StorageDriver {
  return {
    name,
    isAvailable: () => true,
    get: () => value,
    set: vi.fn(),
    remove: vi.fn(),
  };
}

/** 延迟 delayMs 后才返回值的通道。 */
function slowDriver(name: string, value: string | null, delayMs: number): StorageDriver {
  return {
    name,
    isAvailable: () => true,
    get: () =>
      new Promise<string | null>((resolve) => {
        setTimeout(() => resolve(value), delayMs);
      }),
    set: vi.fn(),
    remove: vi.fn(),
  };
}

describe('deadlineMs 未设置', () => {
  it('等齐所有通道（保持原行为）', async () => {
    const outcome = await resolveWinner('k', [
      syncDriver('cookie', null),
      slowDriver('indexedDB', 'v1', 60),
    ]);
    // 慢通道的值被采纳
    expect(outcome.value).toBe('v1');
  });
});

describe('deadlineMs 超时', () => {
  it('不等慢通道，用已读到的通道产出结果', async () => {
    const started = Date.now();
    const outcome = await resolveWinner(
      'k',
      [syncDriver('cookie', 'fast'), slowDriver('indexedDB', 'slow', 500)],
      { deadlineMs: 20 },
    );
    const elapsed = Date.now() - started;

    expect(elapsed).toBeLessThan(200);
    expect(outcome.value).toBe('fast');
  });

  it('慢通道在后台跑完并触发 onSettled，自愈不丢失', async () => {
    const onSettled = vi.fn();
    // 三个通道里两个是慢的且带值，超时时只有 cookie 可见
    await resolveWinner(
      'k',
      [syncDriver('cookie', null), slowDriver('indexedDB', 'restored', 40)],
      { deadlineMs: 10, onSettled },
    );

    // 等后台补齐完成
    await new Promise((r) => setTimeout(r, 120));

    expect(onSettled).toHaveBeenCalledTimes(1);
    const settled = onSettled.mock.calls[0][0];
    // 补齐后拿到慢通道的值——这正是 Evercookie 的恢复能力
    expect(settled.value).toBe('restored');
  });

  it('后台补齐时把值写回缺失的通道（自愈）', async () => {
    const cookie = syncDriver('cookie', null);
    await resolveWinner('k', [cookie, slowDriver('indexedDB', 'restored', 30)], {
      deadlineMs: 10,
      onSettled: () => {},
    });

    await new Promise((r) => setTimeout(r, 120));

    // cookie 通道被补上慢通道恢复出的值
    expect(cookie.set).toHaveBeenCalledWith('k', 'restored');
  });

  it('未超时时不触发 onSettled（避免重复自愈）', async () => {
    const onSettled = vi.fn();
    await resolveWinner('k', [syncDriver('cookie', 'v')], { deadlineMs: 500, onSettled });
    await new Promise((r) => setTimeout(r, 30));
    expect(onSettled).not.toHaveBeenCalled();
  });
});

describe('全通道皆慢', () => {
  it('超时返回 null，不抛错', async () => {
    const outcome = await resolveWinner('k', [slowDriver('indexedDB', 'v', 500)], {
      deadlineMs: 10,
    });
    expect(outcome.value).toBeNull();
  });
});
