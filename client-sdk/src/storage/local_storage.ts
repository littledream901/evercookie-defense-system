/** localStorage 存储驱动。 */

import type { StorageDriver } from './driver_interface';

export const localStorageDriver: StorageDriver = {
  name: 'localStorage',

  isAvailable(): boolean {
    try {
      const testKey = '__sd_test__';
      localStorage.setItem(testKey, '1');
      localStorage.removeItem(testKey);
      return true;
    } catch {
      return false;
    }
  },

  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },

  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      // 静默失败（配额满 / 隐私模式）
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {
      // 静默失败
    }
  },
};
