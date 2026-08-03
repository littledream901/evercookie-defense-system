/** V2 wire 契约的形状锁。
 *
 * 断言 SDK 组装的请求体在**字段名与层级**上与 Python schema 对齐。
 * 编码规则由 `signer.test.ts` 锁，这里锁的是结构——历史上更容易出错的是
 * 把签名字段塞进 `context` 内层，或用 snake_case 写字段名（pydantic 的
 * BaseSchema 用默认 extra="ignore"，写错的字段会被**静默丢弃**而不是报错）。
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildSignPayload } from '../src/core/signer';
import type {
  BehaviorEvent,
  DecisionContext,
  DecisionRequestBody,
  DecisionResponse,
  Mechanism,
  TargetKind,
  Verdict,
} from '../src/types';

/** Python 侧 DecisionContext 的 camelCase alias 全集。 */
const CONTEXT_ALIASES = new Set([
  'appId',
  'ingress',
  'fingerprint',
  'fingerprintIsDerived',
  'deviceId',
  'ip',
  'userAgent',
  'referer',
  'visitUrl',
  'path',
  'method',
  'sessionId',
  'clientLanguage',
  'repeatKey',
  'repeatValue',
  'evercookieRestored',
  'behaviorEvents',
  'extra',
]);

function sampleContext(): DecisionContext {
  return {
    appId: 1,
    ingress: 'sdk',
    fingerprint: 'fp_abc',
    userAgent: 'Mozilla/5.0',
    visitUrl: 'https://shop.example.com/checkout',
    path: '/checkout',
    method: 'GET',
    clientLanguage: 'zh-CN',
    repeatKey: '_sd_0000',
    repeatValue: 'v_abc',
    evercookieRestored: true,
    behaviorEvents: [{ kind: 'click', clientTsMs: 1_700_000_000_000, data: { x: 1, y: 2 } }],
  };
}

describe('DecisionContext 字段名', () => {
  it('全部字段都在 Python alias 集合内', () => {
    for (const key of Object.keys(sampleContext())) {
      expect(CONTEXT_ALIASES, `未知字段 ${key}`).toContain(key);
    }
  });

  it('不使用 snake_case —— 会被 pydantic 静默丢弃', () => {
    for (const key of Object.keys(sampleContext())) {
      expect(key, `${key} 含下划线`).not.toMatch(/_/);
    }
  });
});

describe('签名字段层级', () => {
  it('timestamp / nonce / sign 与 context 同级', () => {
    const body: DecisionRequestBody = {
      context: sampleContext(),
      requireDetails: false,
      timestamp: 1_700_000_000,
      nonce: 'abc',
      sign: 'deadbeef',
    };

    // 网关 _signable_params 读的是顶层键
    expect(Object.keys(body)).toContain('timestamp');
    expect(Object.keys(body)).toContain('nonce');
    expect(Object.keys(body)).toContain('sign');
    // 不能出现在 context 内层
    expect(Object.keys(body.context)).not.toContain('timestamp');
    expect(Object.keys(body.context)).not.toContain('sign');
  });

  it('待签串把 context 编成单个键值对', () => {
    const payload = buildSignPayload({
      context: sampleContext(),
      requireDetails: false,
      timestamp: 1_700_000_000,
      nonce: 'abc',
    });

    // 顶层四个键（requireDetails=false 保留）
    expect(payload.split('&').map((p) => p.split('=')[0])).toEqual([
      'context',
      'nonce',
      'requireDetails',
      'timestamp',
    ]);
  });

  it('context 内层键序不影响签名', () => {
    const forward = sampleContext();
    const reversed = Object.fromEntries(
      Object.entries(forward).reverse(),
    ) as unknown as DecisionContext;

    expect(buildSignPayload({ context: reversed })).toBe(buildSignPayload({ context: forward }));
  });
});

describe('BehaviorEvent 契约', () => {
  it('字段名为 kind / clientTsMs / data', () => {
    const event: BehaviorEvent = { kind: 'click', clientTsMs: 1, data: {} };
    expect(Object.keys(event).sort()).toEqual(['clientTsMs', 'data', 'kind']);
  });

  it('整数时间戳不产生小数点 —— 浮点会破坏与 Python 的一致性', () => {
    const payload = buildSignPayload({
      e: [{ kind: 'click', clientTsMs: 1_700_000_000_000, data: { x: 10 } }],
    });
    expect(decodeURIComponent(payload)).not.toContain('.0');
    expect(decodeURIComponent(payload)).toContain('1700000000000');
  });

  it('浮点数会被序列化成 Python 不一致的形式（记录已知边界）', () => {
    // JS 把 1.0 序列化成 "1"，Python 序列化成 "1.0" —— 故 data 必须用整数
    expect(JSON.stringify({ x: 1.0 })).toBe('{"x":1}');
  });
});

describe('枚举取值与 Python 一致', () => {
  it('Verdict', () => {
    const all: Verdict[] = ['trusted', 'suspect', 'hostile'];
    expect(all).toHaveLength(3);
  });

  it('Mechanism', () => {
    const all: Mechanism[] = ['pass', 'serve_alt', 'redirect', 'challenge', 'deny', 'not_found'];
    expect(all).toHaveLength(6);
  });

  it('TargetKind', () => {
    const all: TargetKind[] = ['origin', 'url', 'page_resource', 'status_only'];
    expect(all).toHaveLength(4);
  });
});

describe('DecisionResponse 字段名', () => {
  it('使用 camelCase alias', () => {
    const response: DecisionResponse = {
      verdict: 'suspect',
      mechanism: 'serve_alt',
      targetKind: 'page_resource',
      targetUrl: 'safe_page',
      httpStatus: 200,
      score: 55,
      ruleIds: [1],
      decidedBy: 'rule',
      decidedStage: 'rule',
      ttlSeconds: 300,
      details: [],
      shadow: [],
      pageContent: '<html></html>',
    };
    for (const key of Object.keys(response)) {
      expect(key, `${key} 含下划线`).not.toMatch(/_/);
    }
  });
});

describe('向量文件覆盖真实请求形状', () => {
  it('包含 decide_body_shape 用例', () => {
    const fixture = JSON.parse(
      readFileSync(join(__dirname, 'fixtures/sign_vectors.json'), 'utf-8'),
    ) as { vectors: Array<{ name: string; params: Record<string, unknown> }> };

    const vector = fixture.vectors.find((v) => v.name === 'decide_body_shape');
    expect(vector).toBeDefined();
    // 该用例必须体现顶层签名字段的层级
    expect(Object.keys(vector!.params)).toContain('timestamp');
    expect(Object.keys(vector!.params)).toContain('nonce');
    expect(Object.keys(vector!.params)).toContain('context');
  });
});
