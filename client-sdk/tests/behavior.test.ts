/** 行为采集器：事件形状必须符合网关 BehaviorEvent 契约。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BehaviorCollector } from '../src/core/behavior';
import type { BehaviorKind } from '../src/types';

const VALID_KINDS: BehaviorKind[] = [
  'page_view',
  'click',
  'mouse_move',
  'scroll',
  'key_press',
  'focus',
  'blur',
  'submit',
];

let collector: BehaviorCollector;

afterEach(() => {
  collector?.destroy();
  vi.useRealTimers();
});

describe('事件形状符合网关契约', () => {
  beforeEach(() => {
    collector = new BehaviorCollector();
    collector.start();
  });

  it('start 立即产出 page_view', () => {
    const events = collector.peek();
    expect(events).toHaveLength(1);
    expect(events[0]!.kind).toBe('page_view');
  });

  it('每条事件都有 kind / clientTsMs / data', () => {
    collector.record('click', { x: 1, y: 2 });
    for (const event of collector.peek()) {
      expect(VALID_KINDS).toContain(event.kind);
      expect(Number.isInteger(event.clientTsMs)).toBe(true);
      expect(event.clientTsMs).toBeGreaterThan(0);
      expect(typeof event.data).toBe('object');
    }
  });

  it('data 的值只含整数 / 字符串 / 布尔 —— 浮点会破坏验签', () => {
    collector.record('mouse_move', { x: 10, y: 20 });
    collector.record('scroll', { y: 100, depth: 50 });

    for (const event of collector.peek()) {
      for (const value of Object.values(event.data)) {
        if (typeof value === 'number') {
          expect(Number.isInteger(value)).toBe(true);
        } else {
          expect(['string', 'boolean']).toContain(typeof value);
        }
      }
    }
  });

  it('鼠标坐标取整', () => {
    document.dispatchEvent(
      new MouseEvent('mousemove', { clientX: 10.7, clientY: 20.2, bubbles: true }),
    );
    const moves = collector.peek().filter((e) => e.kind === 'mouse_move');
    expect(moves).toHaveLength(1);
    expect(moves[0]!.data.x).toBe(11);
    expect(moves[0]!.data.y).toBe(20);
  });
});

describe('隐私边界', () => {
  beforeEach(() => {
    collector = new BehaviorCollector();
    collector.start();
  });

  it('按键只记类别，绝不记录实际字符', () => {
    // 用 z / 7 这类不出现在 data 字段名里的字符，避免误判
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', bubbles: true }));
    const keys = collector.peek().filter((e) => e.kind === 'key_press');

    expect(keys).toHaveLength(1);
    expect(keys[0]!.data.category).toBe('letter');
    expect(JSON.stringify(keys[0]!.data)).not.toContain('z');
  });

  it('密码类输入的字符不进入事件载荷', () => {
    const secret = 'Hunter2!';
    const c = new BehaviorCollector({ sampleIntervalMs: 0 });
    c.start();
    for (const ch of secret) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true }));
    }

    const keyEvents = c.peek().filter((e) => e.kind === 'key_press');
    expect(keyEvents).toHaveLength(secret.length);

    // data 的取值只能落在固定的类别词表里；任何原始字符都会以「不在词表中」暴露
    const allowed = new Set(['digit', 'letter', 'symbol', 'delete', 'commit', 'arrow', 'control']);
    for (const event of keyEvents) {
      expect(Object.keys(event.data).sort()).toEqual(['category', 'repeat']);
      expect(allowed).toContain(event.data.category);
      expect(typeof event.data.repeat).toBe('boolean');
    }
    c.destroy();
  });

  it('按键类别归类正确', () => {
    const cases: Array<[string, string]> = [
      ['5', 'digit'],
      ['a', 'letter'],
      ['@', 'symbol'],
      ['Backspace', 'delete'],
      ['Enter', 'commit'],
      ['ArrowLeft', 'arrow'],
      ['Shift', 'control'],
    ];

    for (const [key, expected] of cases) {
      const c = new BehaviorCollector({ sampleIntervalMs: 0 });
      c.start();
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      const events = c.peek().filter((e) => e.kind === 'key_press');
      expect(events[0]?.data.category, `key=${key}`).toBe(expected);
      c.destroy();
    }
  });

  it('点击只记标签名，不记 id / class / 文本', () => {
    const button = document.createElement('button');
    button.id = 'secret-id';
    button.className = 'secret-class';
    button.textContent = 'secret text';
    document.body.appendChild(button);

    button.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    const clicks = collector.peek().filter((e) => e.kind === 'click');
    expect(clicks).toHaveLength(1);
    const serialized = JSON.stringify(clicks[0]!.data);
    expect(clicks[0]!.data.tag).toBe('button');
    expect(serialized).not.toContain('secret-id');
    expect(serialized).not.toContain('secret-class');
    expect(serialized).not.toContain('secret text');

    button.remove();
  });
});

describe('采样与上限', () => {
  it('高频同类事件按间隔节流', () => {
    vi.useFakeTimers();
    collector = new BehaviorCollector({ sampleIntervalMs: 200 });
    collector.start();

    for (let i = 0; i < 10; i++) {
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: i, bubbles: true }));
    }
    expect(collector.peek().filter((e) => e.kind === 'mouse_move')).toHaveLength(1);

    vi.advanceTimersByTime(250);
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 99, bubbles: true }));
    expect(collector.peek().filter((e) => e.kind === 'mouse_move')).toHaveLength(2);
  });

  it('低频关键事件不被节流', () => {
    collector = new BehaviorCollector({ sampleIntervalMs: 10000 });
    collector.start();

    collector.record('submit', {});
    collector.record('submit', {});

    expect(collector.peek().filter((e) => e.kind === 'submit')).toHaveLength(2);
  });

  it('超过 maxEvents 丢最旧，保留最近事件', () => {
    collector = new BehaviorCollector({ sampleIntervalMs: 0, maxEvents: 5 });
    collector.start();

    for (let i = 0; i < 20; i++) {
      collector.record('click', { seq: i });
    }

    const events = collector.peek();
    expect(events).toHaveLength(5);
    // 最后一条必须是最新的
    expect(events[events.length - 1]!.data.seq).toBe(19);
  });

  it('缓冲上限保证不超过网关单请求上限', () => {
    collector = new BehaviorCollector({ sampleIntervalMs: 0, maxEvents: 64 });
    collector.start();
    for (let i = 0; i < 500; i++) collector.record('click', { seq: i });
    expect(collector.size).toBeLessThanOrEqual(64);
  });
});

describe('drain / destroy', () => {
  it('drain 取出并清空缓冲', () => {
    collector = new BehaviorCollector();
    collector.start();
    collector.record('click', {});

    const first = collector.drain();
    expect(first.length).toBeGreaterThan(0);
    expect(collector.drain()).toHaveLength(0);
  });

  it('peek 不清空缓冲', () => {
    collector = new BehaviorCollector();
    collector.start();
    expect(collector.peek()).toHaveLength(1);
    expect(collector.peek()).toHaveLength(1);
  });

  it('enabled=false 时不采集任何事件', () => {
    collector = new BehaviorCollector({ enabled: false });
    collector.start();
    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
    collector.record('click', {});
    expect(collector.peek()).toHaveLength(0);
  });

  it('destroy 后不再响应事件', () => {
    collector = new BehaviorCollector({ sampleIntervalMs: 0 });
    collector.start();
    collector.destroy();

    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
    expect(collector.peek()).toHaveLength(0);
  });

  it('重复 start 不重复绑定监听', () => {
    collector = new BehaviorCollector({ sampleIntervalMs: 0 });
    collector.start();
    collector.start();
    collector.drain();

    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 1, bubbles: true }));
    expect(collector.peek().filter((e) => e.kind === 'mouse_move')).toHaveLength(1);
  });
});
