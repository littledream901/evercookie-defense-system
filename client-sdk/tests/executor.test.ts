/** 处置执行器：机制映射与跳转协议白名单。 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { applyDecision } from '../src/core/executor';
import type { DecisionResponse, Mechanism } from '../src/types';

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

let replace: ReturnType<typeof vi.fn>;

beforeEach(() => {
  document.body.innerHTML = '';
  replace = vi.fn();
  // jsdom 不允许直接赋值 location.href，替换整个对象
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { href: 'https://shop.example.com/checkout', replace },
  });
});

describe('pass', () => {
  it('不干预页面', () => {
    const outcome = applyDecision(decision({ mechanism: 'pass' }));
    expect(outcome).toEqual({ applied: false, action: 'none' });
    expect(document.body.innerHTML).toBe('');
    expect(replace).not.toHaveBeenCalled();
  });
});

describe('redirect', () => {
  it('跳转到 targetUrl', () => {
    const outcome = applyDecision(
      decision({ mechanism: 'redirect', targetUrl: 'https://safe.example.com/', httpStatus: 302 }),
    );
    expect(outcome.action).toBe('redirect');
    expect(replace).toHaveBeenCalledWith('https://safe.example.com/');
  });

  it('接受相对路径', () => {
    applyDecision(decision({ mechanism: 'redirect', targetUrl: '/blocked' }));
    expect(replace).toHaveBeenCalledWith('/blocked');
  });

  it('拒绝 javascript: 伪协议，退化为阻断', () => {
    const outcome = applyDecision(
      decision({ mechanism: 'redirect', targetUrl: 'javascript:alert(1)' }),
    );
    expect(outcome.action).toBe('block');
    expect(replace).not.toHaveBeenCalled();
    expect(document.querySelector('[data-sd-overlay]')).not.toBeNull();
  });

  it('拒绝 data: 伪协议', () => {
    const outcome = applyDecision(
      decision({ mechanism: 'redirect', targetUrl: 'data:text/html,<script>x</script>' }),
    );
    expect(outcome.action).toBe('block');
    expect(replace).not.toHaveBeenCalled();
  });

  it('缺少 targetUrl 时阻断而非放行', () => {
    const outcome = applyDecision(decision({ mechanism: 'redirect', targetUrl: null }));
    expect(outcome.action).toBe('block');
    expect(replace).not.toHaveBeenCalled();
  });
});

describe('serve_alt', () => {
  it('缺少 pageContent 但有安全 targetUrl 时退化为跳转', () => {
    const outcome = applyDecision(
      decision({ mechanism: 'serve_alt', pageContent: null, targetUrl: 'https://alt.example.com/' }),
    );
    expect(outcome.action).toBe('redirect');
    expect(replace).toHaveBeenCalledWith('https://alt.example.com/');
  });

  it('既无 pageContent 也无 targetUrl 时阻断，不能当放行', () => {
    const outcome = applyDecision(
      decision({ mechanism: 'serve_alt', pageContent: null, targetUrl: null }),
    );
    expect(outcome.applied).toBe(true);
    expect(outcome.action).toBe('block');
  });
});

describe('challenge', () => {
  it('渲染校验遮罩并触发钩子', () => {
    const onChallenge = vi.fn();
    const d = decision({ mechanism: 'challenge', challengeKind: 'captcha', httpStatus: 403 });

    const outcome = applyDecision(d, { onChallenge });

    expect(outcome.action).toBe('challenge');
    expect(onChallenge).toHaveBeenCalledWith(d);
    expect(document.querySelector('[data-sd-overlay]')?.textContent).toContain('人机校验');
  });

  it('challengeKind=js 时文案对应 JS 校验', () => {
    applyDecision(decision({ mechanism: 'challenge', challengeKind: 'js' }));
    expect(document.querySelector('[data-sd-overlay]')?.textContent).toContain('JS 校验');
  });
});

describe('deny / not_found', () => {
  it('deny 渲染拒绝页', () => {
    const outcome = applyDecision(decision({ mechanism: 'deny', httpStatus: 403 }));
    expect(outcome.action).toBe('block');
    expect(document.querySelector('[data-sd-overlay]')?.textContent).toContain('访问被拒绝');
  });

  it('not_found 渲染 404 文案', () => {
    applyDecision(decision({ mechanism: 'not_found', httpStatus: 404 }));
    const text = document.querySelector('[data-sd-overlay]')?.textContent ?? '';
    expect(text).toContain('页面不存在');
    expect(text).toContain('404');
  });

  it('遮罩置于最高层级，防止被站点样式盖住', () => {
    applyDecision(decision({ mechanism: 'deny' }));
    const overlay = document.querySelector('[data-sd-overlay]') as HTMLElement;
    expect(overlay.style.zIndex).toBe('2147483647');
    expect(overlay.style.position).toBe('fixed');
  });
});

describe('onDecision 钩子', () => {
  it('返回 true 时执行器不动 DOM', () => {
    const outcome = applyDecision(decision({ mechanism: 'deny' }), {
      onDecision: () => true,
    });
    expect(outcome).toEqual({ applied: false, action: 'skipped' });
    expect(document.querySelector('[data-sd-overlay]')).toBeNull();
  });

  it('返回 undefined 时正常执行', () => {
    const onDecision = vi.fn();
    const outcome = applyDecision(decision({ mechanism: 'deny' }), { onDecision });
    expect(onDecision).toHaveBeenCalled();
    expect(outcome.action).toBe('block');
  });
});

describe('全机制覆盖', () => {
  it('每种 mechanism 都有明确处理，不落到 default', () => {
    const mechanisms: Mechanism[] = [
      'pass',
      'serve_alt',
      'redirect',
      'challenge',
      'deny',
      'not_found',
    ];
    for (const mechanism of mechanisms) {
      document.body.innerHTML = '';
      const outcome = applyDecision(
        decision({
          mechanism,
          targetUrl: 'https://alt.example.com/',
          pageContent: mechanism === 'serve_alt' ? null : undefined,
          challengeKind: mechanism === 'challenge' ? 'captcha' : null,
        }),
      );
      if (mechanism === 'pass') {
        // pass 是唯一不干预的机制
        expect(outcome.action).toBe('none');
        continue;
      }
      expect(outcome.action, mechanism).not.toBe('none');
      expect(outcome.applied, mechanism).toBe(true);
    }
  });
});
