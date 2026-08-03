/** 行为时序采集器。
 *
 * 与 V1 的关键差异：产出的是网关契约里的 `BehaviorEvent`（kind + clientTsMs
 * + data），而不是 V1 那种自定义的 `BehaviorFragment` 聚合结构。V1 的片段
 * 结构网关根本无法解析，是一条死路。
 *
 * 采样与上限
 * ----------
 * `mousemove` / `scroll` 触发频率极高，全量上报会打满网关。这里做两层节流：
 * 1. 采样：同类事件最小间隔 `sampleIntervalMs`，其间的事件直接丢弃。
 * 2. 缓冲上限：`maxEvents` 满了就丢**最旧**的——风控关心的是近期行为。
 */

import type { BehaviorEvent, BehaviorKind, BehaviorScalar } from '../types';

export interface BehaviorConfig {
  enabled: boolean;
  /** 同类事件的最小采样间隔（毫秒）。 */
  sampleIntervalMs: number;
  /** 缓冲区事件上限，与网关 `MAX_BEHAVIOR_EVENTS_PER_REQUEST` 对齐。 */
  maxEvents: number;
}

export const DEFAULT_BEHAVIOR_CONFIG: BehaviorConfig = {
  enabled: true,
  sampleIntervalMs: 200,
  maxEvents: 64,
};

type Listener = { target: EventTarget; type: string; handler: EventListener };

export class BehaviorCollector {
  private config: BehaviorConfig;
  private events: BehaviorEvent[] = [];
  private lastSampleAt: Partial<Record<BehaviorKind, number>> = {};
  private listeners: Listener[] = [];
  private startedAt = Date.now();
  private running = false;

  constructor(config: Partial<BehaviorConfig> = {}) {
    this.config = { ...DEFAULT_BEHAVIOR_CONFIG, ...config };
  }

  /** 绑定事件监听并开始采集。重复调用无副作用。 */
  start(): void {
    if (this.running || !this.config.enabled) return;
    if (typeof document === 'undefined') return;

    this.running = true;
    this.startedAt = Date.now();

    this.record('page_view', {
      url: location.href.slice(0, 512),
      referrer: document.referrer.slice(0, 512),
    });

    this.bind(document, 'mousemove', (e) => {
      const me = e as MouseEvent;
      this.record('mouse_move', { x: Math.round(me.clientX), y: Math.round(me.clientY) });
    });

    this.bind(document, 'click', (e) => {
      const me = e as MouseEvent;
      this.record('click', {
        x: Math.round(me.clientX),
        y: Math.round(me.clientY),
        // 只记标签名，不记 id/class/文本——避免把用户输入或业务数据带出页面
        tag: (me.target as Element | null)?.tagName?.toLowerCase() ?? '',
      });
    });

    this.bind(window, 'scroll', () => {
      this.record('scroll', {
        y: Math.round(window.scrollY),
        depth: this.scrollDepth(),
      });
    });

    this.bind(document, 'keydown', (e) => {
      const ke = e as KeyboardEvent;
      // 只记按键类别，绝不记录实际字符——记了就是在采集用户输入内容
      this.record('key_press', {
        category: keyCategory(ke.key),
        repeat: ke.repeat,
      });
    });

    this.bind(window, 'focus', () => this.record('focus', { stayMs: this.stayMs() }));
    this.bind(window, 'blur', () => this.record('blur', { stayMs: this.stayMs() }));

    this.bind(document, 'submit', (e) => {
      this.record('submit', {
        // 同上：只记表单的 method/action 主机名，不记字段
        method: ((e.target as HTMLFormElement | null)?.method ?? '').toLowerCase(),
        stayMs: this.stayMs(),
      });
    });
  }

  /** 取出全部事件并清空缓冲。用于随 decide / heartbeat 上报。 */
  drain(): BehaviorEvent[] {
    const drained = this.events;
    this.events = [];
    return drained;
  }

  /** 只读快照，不清空缓冲。 */
  peek(): BehaviorEvent[] {
    return [...this.events];
  }

  get size(): number {
    return this.events.length;
  }

  /** 解绑全部监听并清空缓冲。 */
  destroy(): void {
    for (const { target, type, handler } of this.listeners) {
      target.removeEventListener(type, handler);
    }
    this.listeners = [];
    this.events = [];
    this.lastSampleAt = {};
    this.running = false;
  }

  /** 手动记录一条事件（供业务侧标注关键动作）。 */
  record(kind: BehaviorKind, data: Record<string, BehaviorScalar> = {}): void {
    if (!this.config.enabled) return;

    const now = Date.now();
    const last = this.lastSampleAt[kind];
    // page_view / submit 这类低频关键事件不做采样节流
    const throttled = kind === 'mouse_move' || kind === 'scroll' || kind === 'key_press';
    if (throttled && last !== undefined && now - last < this.config.sampleIntervalMs) {
      return;
    }
    this.lastSampleAt[kind] = now;

    this.events.push({ kind, clientTsMs: now, data });

    if (this.events.length > this.config.maxEvents) {
      // 丢最旧：风控看的是近期行为，且网关按 maxEvents 截断请求
      this.events = this.events.slice(-this.config.maxEvents);
    }
  }

  private bind(target: EventTarget, type: string, handler: EventListener): void {
    target.addEventListener(type, handler, { passive: true });
    this.listeners.push({ target, type, handler });
  }

  private stayMs(): number {
    return Date.now() - this.startedAt;
  }

  private scrollDepth(): number {
    try {
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 0) return 0;
      return Math.round((window.scrollY / scrollable) * 100);
    } catch {
      return 0;
    }
  }
}

/** 按键归类。刻意粗粒度——细到具体字符就是在记录用户输入。 */
function keyCategory(key: string): string {
  if (key.length === 1) {
    if (/[0-9]/.test(key)) return 'digit';
    if (/[a-z]/i.test(key)) return 'letter';
    return 'symbol';
  }
  if (key === 'Backspace' || key === 'Delete') return 'delete';
  if (key === 'Enter' || key === 'Tab') return 'commit';
  if (key.startsWith('Arrow')) return 'arrow';
  return 'control';
}
