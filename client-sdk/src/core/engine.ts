/** 投票与自愈引擎。
 *
 * Evercookie 的核心：同一值写入 N 个存储通道，读取时取多数值，并把多数值
 * 回写到不一致的通道。用户清掉部分通道后，剩余通道能把身份恢复回来。
 */

import type { StorageDriver } from '../storage/driver_interface';

export interface VoteResult {
  winner: string | null;
  /** 胜出值在有效票中的占比，0~1。 */
  confidence: number;
  distribution: Record<string, number>;
  /** 是否发生过自愈（有通道与胜出值不一致）。 */
  healed: boolean;
}

/** 对各通道读到的值投票，选出多数值。 */
export function vote(values: Record<string, string | null>): VoteResult {
  const counts: Record<string, number> = {};
  let total = 0;

  for (const driverName of Object.keys(values)) {
    const val = values[driverName];
    if (val === null || val === undefined || val === '') continue;
    counts[val] = (counts[val] ?? 0) + 1;
    total++;
  }

  if (total === 0) {
    return { winner: null, confidence: 0, distribution: {}, healed: false };
  }

  let winner: string | null = null;
  let maxCount = 0;
  // 平票时取字典序最小的值，保证多次调用结果稳定——依赖对象键序会让
  // 同一组输入在不同浏览器上选出不同赢家。
  for (const val of Object.keys(counts).sort()) {
    const count = counts[val] as number;
    if (count > maxCount) {
      maxCount = count;
      winner = val;
    }
  }

  return {
    winner,
    confidence: maxCount / total,
    distribution: counts,
    healed: maxCount < Object.keys(values).length,
  };
}

/** 自愈：把胜出值写回所有与之不一致的通道。 */
export function selfHeal(
  key: string,
  winner: string,
  storageMap: Record<string, StorageDriver>,
  values: Record<string, string | null>,
): string[] {
  const healed: string[] = [];
  for (const driverName of Object.keys(values)) {
    if (values[driverName] === winner) continue;
    const driver = storageMap[driverName];
    if (!driver) continue;
    try {
      void driver.set(key, winner);
      healed.push(driverName);
    } catch {
      // 静默失败：单通道写不进去不影响整体
    }
  }
  return healed;
}

export interface ResolveOutcome {
  value: string | null;
  /** 是否由自愈恢复（存在通道缺失或不一致）。用于上报 `evercookieRestored`。 */
  restored: boolean;
  confidence: number;
}

export interface ResolveOptions {
  /**
   * 读取阶段的软上限（毫秒）。0 / 省略表示不限时（原行为）。
   *
   * 存在原因：`indexedDB` 与 `cacheStorage` 是异步通道，正常 1~10ms，但在隐私
   * 模式、磁盘繁忙或 Safari 的存储分区下可能显著变慢。决策链路上跳转判断要压进
   * 100ms，不能被单个慢通道拖住。
   *
   * 超时**不是放弃**：已读到的通道先投票产出结果，未完成的通道继续在后台跑完
   * 并参与自愈。因此 Evercookie 的「清掉部分通道仍能恢复身份」语义不受损——
   * 只是这一次的恢复可能落在下一次请求生效。
   */
  deadlineMs?: number;
  /** 后台补齐完成后的回调，携带补齐后的胜出值。 */
  onSettled?: (outcome: ResolveOutcome) => void;
}

/** 解析主值：全通道读取 → 投票 → 自愈 → 返回胜出值。 */
export async function resolveWinner(
  key: string,
  drivers: StorageDriver[],
  options: ResolveOptions = {},
): Promise<ResolveOutcome> {
  const values: Record<string, string | null> = {};
  const storageMap: Record<string, StorageDriver> = {};

  const readAll = Promise.all(
    drivers.map(async (driver) => {
      let available: boolean;
      try {
        available = await driver.isAvailable();
      } catch {
        available = false;
      }

      if (!available) {
        // 不可用通道不计入 values：它既不投票也不参与自愈统计
        return;
      }

      storageMap[driver.name] = driver;
      try {
        values[driver.name] = await driver.get(key);
      } catch {
        values[driver.name] = null;
      }
    }),
  );

  /** 对当前已读到的 values 投票并自愈。 */
  const settle = (): ResolveOutcome => {
    const result = vote(values);
    if (result.winner !== null) {
      selfHeal(key, result.winner, storageMap, values);
    }
    return {
      value: result.winner,
      restored: result.winner !== null && result.healed,
      confidence: result.confidence,
    };
  };

  const deadline = options.deadlineMs ?? 0;
  if (deadline <= 0) {
    await readAll;
    return settle();
  }

  let timer: ReturnType<typeof setTimeout> | undefined;
  const timedOut = await Promise.race([
    readAll.then(() => false),
    new Promise<boolean>((resolve) => {
      timer = setTimeout(() => resolve(true), deadline);
    }),
  ]);
  if (timer) clearTimeout(timer);

  if (!timedOut) return settle();

  // 慢通道还在跑：先用已读到的通道给出结果，不阻塞调用方。
  const partial = settle();
  // 后台跑完后再投一次票并自愈，把慢通道的值补进来。
  void readAll.then(() => {
    try {
      options.onSettled?.(settle());
    } catch {
      // 回调异常不能影响存储层
    }
  });
  return partial;
}
