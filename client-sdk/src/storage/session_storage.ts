/** sessionStorage 存储驱动。 */

import type { StorageDriver } from './driver_interface';

export const sessionStorageDriver: StorageDriver = {
  name: 'sessionStorage',

  isAvailable(): boolean {
    try {
      const testKey = '__sd_test__';
      sessionStorage.setItem(testKey, '1');
      sessionStorage.removeItem(testKey);
      return true;
    } catch {
      return false;
    }
  },

  get(key: string): string | null {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  },

  set(key: string, value: string): void {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      // 静默失败
    }
  },

  remove(key: string): void {
    try {
      sessionStorage.removeItem(key);
    } catch {
      // 静默失败
    }
  },
};
