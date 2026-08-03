/** Cookie 存储驱动。 */

import type { StorageDriver } from './driver_interface';

const COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60; // 10 年

function parseCookies(): Record<string, string> {
  const result: Record<string, string> = {};
  const cookieStr = typeof document === 'undefined' ? '' : document.cookie;
  if (!cookieStr) return result;

  for (const part of cookieStr.split(';')) {
    const idx = part.indexOf('=');
    if (idx === -1) continue;
    const key = part.substring(0, idx).trim();
    const value = part.substring(idx + 1).trim();
    if (!key) continue;
    try {
      result[decodeURIComponent(key)] = decodeURIComponent(value);
    } catch {
      // 非法百分号编码的 cookie（他方写入）跳过，不影响自家键位
      result[key] = value;
    }
  }
  return result;
}

export const cookieDriver: StorageDriver = {
  name: 'cookie',

  isAvailable(): boolean {
    try {
      if (typeof document === 'undefined') return false;
      // 写探针而不是判断 document.cookie 非空：新访客的 cookie 本来就是空串，
      // V1 用 `!!document.cookie` 判断可用性，导致首访时 cookie 通道被误判不可用。
      const probe = '__sd_probe__';
      document.cookie = `${probe}=1; path=/; SameSite=Lax`;
      const ok = document.cookie.includes(probe);
      document.cookie = `${probe}=; path=/; max-age=0`;
      return ok;
    } catch {
      return false;
    }
  },

  get(key: string): string | null {
    const cookies = parseCookies();
    return key in cookies ? (cookies[key] as string) : null;
  },

  set(key: string, value: string): void {
    try {
      const encoded = encodeURIComponent(value);
      document.cookie = `${encodeURIComponent(key)}=${encoded}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
    } catch {
      // 静默失败
    }
  },

  remove(key: string): void {
    try {
      document.cookie = `${encodeURIComponent(key)}=; path=/; max-age=0`;
    } catch {
      // 静默失败
    }
  },
};
