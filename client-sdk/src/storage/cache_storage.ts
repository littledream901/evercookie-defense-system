/** Cache API 存储驱动。
 *
 * 把值包装成 `Response` 放进 Cache，URL 形如 `/sdCache/{key}`。
 * 该路径不会真的发起网络请求——Cache API 只把它当键位用。
 */

import type { StorageDriver } from './driver_interface';

const CACHE_NAME = 'sdCache';

function toCacheURL(key: string): string {
  return `/sdCache/${encodeURIComponent(key)}`;
}

export const cacheStorageDriver: StorageDriver = {
  name: 'cacheStorage',

  isAvailable(): boolean {
    try {
      // Cache API 在非安全上下文（http 且非 localhost）下不存在
      return typeof caches !== 'undefined';
    } catch {
      return false;
    }
  },

  async get(key: string): Promise<string | null> {
    try {
      const cache = await caches.open(CACHE_NAME);
      const response = await cache.match(toCacheURL(key));
      if (!response) return null;
      return await response.text();
    } catch {
      return null;
    }
  },

  async set(key: string, value: string): Promise<void> {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(
        toCacheURL(key),
        new Response(value, { status: 200, headers: { 'Content-Type': 'text/plain' } }),
      );
    } catch {
      // 静默失败
    }
  },

  async remove(key: string): Promise<void> {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.delete(toCacheURL(key));
    } catch {
      // 静默失败
    }
  },
};
