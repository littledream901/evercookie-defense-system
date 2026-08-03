/** window.name 存储驱动。
 *
 * 以 `k=v&k=v` 编码存在 `window.name`。特点是跨同标签页导航持久，刷新后仍在，
 * 但换标签页即丢失——投票时它的权重与其他通道相同，属于设计取舍。
 */

import type { StorageDriver } from './driver_interface';

function parseWindowName(): Record<string, string> {
  const raw = window.name || '';
  const result: Record<string, string> = {};
  if (!raw) return result;

  for (const pair of raw.split('&')) {
    const idx = pair.indexOf('=');
    if (idx === -1) continue;
    try {
      const key = decodeURIComponent(pair.substring(0, idx));
      if (key) {
        result[key] = decodeURIComponent(pair.substring(idx + 1));
      }
    } catch {
      // 非本 SDK 写入的内容，跳过
    }
  }
  return result;
}

function writeWindowName(data: Record<string, string>): void {
  const pairs: string[] = [];
  for (const key of Object.keys(data)) {
    pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(data[key] as string)}`);
  }
  window.name = pairs.join('&');
}

export const windowNameDriver: StorageDriver = {
  name: 'windowName',

  isAvailable(): boolean {
    try {
      return typeof window !== 'undefined' && 'name' in window;
    } catch {
      return false;
    }
  },

  get(key: string): string | null {
    try {
      const data = parseWindowName();
      return key in data ? (data[key] as string) : null;
    } catch {
      return null;
    }
  },

  set(key: string, value: string): void {
    try {
      const data = parseWindowName();
      data[key] = value;
      writeWindowName(data);
    } catch {
      // 静默失败
    }
  },

  remove(key: string): void {
    try {
      const data = parseWindowName();
      delete data[key];
      writeWindowName(data);
    } catch {
      // 静默失败
    }
  },
};
