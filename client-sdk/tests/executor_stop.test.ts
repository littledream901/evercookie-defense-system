/** 跳转优先级：干预分支要掐掉在途请求，放行分支绝不能碰。
 *
 * `location.replace` 会终止导航，但在它生效前已发起的图片/脚本/XHR 仍占用连接，
 * 表现为「跳转前还在把整站资源拉完」。因此干预分支先调 `window.stop()`。
 *
 * 反向约束同样重要：`pass` 分支若调用 stop()，会打断正常访客的页面加载。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { applyDecision } from '../src/core/executor';
import type { DecisionResponse } from '../src/types';

function decision(overrides: Partial<DecisionResponse> = {}): DecisionResponse {
  return {
    verdict: 'trusted',
    mechanism: 'pass',
    targetKind: 'origin',
    httpStatus: 200,
    score: 0,
    ruleIds: [],
    decidedBy: 'test',
    decidedStage: 'test',
    ttlSeconds: 300,
    details: [],
    shadow: [],
    ...overrides,
  };
}

let stop: ReturnType<typeof vi.fn>;
let replace: ReturnType<typeof vi.fn>;

beforeEach(() => {
  document.body.innerHTML = '';
  replace = vi.fn();
  stop = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { href: 'https://shop.example.com/checkout', replace },
  });
  Object.defineProperty(window, 'stop', { configurable: true, writable: true, value: stop });
});

describe('干预分支中止加载', () => {
  it('redirect：先 stop 再跳', () => {
    applyDecision(decision({ mechanism: 'redirect', targetUrl: 'https://safe.example.com/' }));

    expect(stop).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith('https://safe.example.com/');
    // 顺序：stop 必须在 replace 之前，否则在途请求已经跑完了
    expect(stop.mock.invocationCallOrder[0]).toBeLessThan(replace.mock.invocationCallOrder[0]);
  });

  it('serve_alt 缺内容退化为跳转时同样 stop', () => {
    applyDecision(
      decision({ mechanism: 'serve_alt', pageContent: null, targetUrl: 'https://alt.example.com/' }),
    );
    expect(stop).toHaveBeenCalled();
  });

  it('deny：遮罩前先 stop，避免资源在后台继续下载', () => {
    applyDecision(decision({ mechanism: 'deny', httpStatus: 403 }));
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('not_found 同样 stop', () => {
    applyDecision(decision({ mechanism: 'not_found', httpStatus: 404 }));
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it('targetUrl 非法退化为阻断时也 stop', () => {
    applyDecision(decision({ mechanism: 'redirect', targetUrl: 'javascript:alert(1)' }));
    expect(stop).toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });
});

describe('放行分支不得干预加载', () => {
  it('pass 不调用 stop —— 正常访客的渲染流程不受影响', () => {
    const outcome = applyDecision(decision({ mechanism: 'pass' }));
    expect(outcome.action).toBe('none');
    expect(stop).not.toHaveBeenCalled();
  });

  it('onDecision 接管（返回 true）时不调用 stop', () => {
    applyDecision(decision({ mechanism: 'redirect', targetUrl: 'https://x.example.com/' }), {
      onDecision: () => true,
    });
    expect(stop).not.toHaveBeenCalled();
  });

  it('未知机制不调用 stop', () => {
    applyDecision(decision({ mechanism: 'brand_new' as DecisionResponse['mechanism'] }));
    expect(stop).not.toHaveBeenCalled();
  });
});

describe('window.stop 不可用时的兼容性', () => {
  it('缺少 window.stop 不抛错，跳转照常执行', () => {
    Object.defineProperty(window, 'stop', {
      configurable: true,
      writable: true,
      value: undefined,
    });

    expect(() =>
      applyDecision(decision({ mechanism: 'redirect', targetUrl: 'https://safe.example.com/' })),
    ).not.toThrow();
    expect(replace).toHaveBeenCalledWith('https://safe.example.com/');
  });

  it('stop 抛异常时不影响跳转', () => {
    Object.defineProperty(window, 'stop', {
      configurable: true,
      writable: true,
      value: () => {
        throw new Error('cross-origin iframe');
      },
    });

    expect(() =>
      applyDecision(decision({ mechanism: 'redirect', targetUrl: 'https://safe.example.com/' })),
    ).not.toThrow();
    expect(replace).toHaveBeenCalledWith('https://safe.example.com/');
  });
});

describe('head 同步阶段渲染遮罩', () => {
  it('body 不存在时挂到 documentElement，遮罩不丢失', () => {
    // 模拟 head 内同步执行：此时解析器还没产出 body
    const body = document.body;
    body.remove();
    expect(document.body).toBeNull();

    applyDecision(decision({ mechanism: 'deny', httpStatus: 403 }));

    const overlay = document.querySelector('[data-sd-overlay]');
    expect(overlay).not.toBeNull();
    expect(overlay?.parentElement).toBe(document.documentElement);

    document.documentElement.appendChild(body);
  });

  it('body 出现后把遮罩迁移过去', async () => {
    const body = document.body;
    body.remove();

    applyDecision(decision({ mechanism: 'deny' }));
    const overlay = document.querySelector('[data-sd-overlay]');

    // body 解析完成
    document.documentElement.appendChild(body);
    document.dispatchEvent(new Event('DOMContentLoaded'));

    expect(overlay?.parentElement).toBe(document.body);
  });
});
