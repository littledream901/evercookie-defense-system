/** 存储驱动接口。
 *
 * 同步驱动（cookie / localStorage / windowName）与异步驱动（indexedDB /
 * cacheStorage）共用同一接口，返回值联合了 Promise 与裸值，由调用方统一
 * `await`——对同步驱动 `await` 裸值是无害的。
 */

export interface StorageDriver {
  name: string;
  isAvailable(): Promise<boolean> | boolean;
  get(key: string): Promise<string | null> | string | null;
  set(key: string, value: string): Promise<void> | void;
  remove(key: string): Promise<void> | void;
}
