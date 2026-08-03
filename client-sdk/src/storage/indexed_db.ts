/** IndexedDB 存储驱动。 */

import type { StorageDriver } from './driver_interface';

const DB_NAME = 'sdCache';
const STORE_NAME = 'sdCookie';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'name' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    // 隐私模式下 open 既不 success 也不 error，只触发 blocked；不挂等待句柄，
    // 由上层 Promise.all 的其他通道推进，避免整个 resolveWinner 卡死。
    request.onblocked = () => reject(new Error('indexedDB blocked'));
  });
}

export const indexedDBDriver: StorageDriver = {
  name: 'indexedDB',

  isAvailable(): boolean {
    try {
      return typeof indexedDB !== 'undefined';
    } catch {
      return false;
    }
  },

  async get(key: string): Promise<string | null> {
    try {
      const db = await openDB();
      return new Promise((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const request = tx.objectStore(STORE_NAME).get(key);
        request.onsuccess = () => {
          const result = request.result as { value?: string } | undefined;
          resolve(result?.value ?? null);
        };
        request.onerror = () => resolve(null);
      });
    } catch {
      return null;
    }
  },

  async set(key: string, value: string): Promise<void> {
    try {
      const db = await openDB();
      return new Promise((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).put({ name: key, value });
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
        tx.onabort = () => resolve();
      });
    } catch {
      // 静默失败
    }
  },

  async remove(key: string): Promise<void> {
    try {
      const db = await openDB();
      return new Promise((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.objectStore(STORE_NAME).delete(key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
        tx.onabort = () => resolve();
      });
    } catch {
      // 静默失败
    }
  },
};
