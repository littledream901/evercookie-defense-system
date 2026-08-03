/** 待签串与签名的跨语言一致性。
 *
 * 向量由 Python 侧 `build_sign_payload` 生成（见 `fixtures/gen_vectors.py`），
 * 本测试断言 TS 实现逐字节一致。任一侧改实现，这里必然先红。
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildSignPayload, generateNonce, signParams } from '../src/core/signer';
import { canonicalJson } from '../src/utils/crypto';

interface Vector {
  name: string;
  note: string;
  params: Record<string, unknown>;
  payload: string;
  sign: string;
}

const fixture = JSON.parse(
  readFileSync(join(__dirname, 'fixtures/sign_vectors.json'), 'utf-8'),
) as { secret: string; vectors: Vector[] };

describe('buildSignPayload 与 Python 逐字节一致', () => {
  it('向量文件非空', () => {
    expect(fixture.vectors.length).toBeGreaterThan(0);
  });

  for (const vector of fixture.vectors) {
    it(`${vector.name}: ${vector.note}`, () => {
      expect(buildSignPayload(vector.params)).toBe(vector.payload);
    });
  }
});

describe('signParams 与 Python HMAC 一致', () => {
  for (const vector of fixture.vectors) {
    it(vector.name, async () => {
      expect(await signParams(vector.params, fixture.secret)).toBe(vector.sign);
    });
  }
});

describe('buildSignPayload 边界', () => {
  it('键按字典序而非插入序', () => {
    expect(buildSignPayload({ b: 1, a: 2 })).toBe('a=2&b=1');
  });

  it('剔除 null / undefined / 空串', () => {
    expect(buildSignPayload({ a: 1, b: null, c: undefined, d: '' })).toBe('a=1');
  });

  it('保留 0 与 false —— 它们是有效取值不是缺失', () => {
    expect(buildSignPayload({ a: 0, b: false })).toBe('a=0&b=false');
  });

  it('排除 sign 自身', () => {
    expect(buildSignPayload({ a: 1, sign: 'x' })).toBe('a=1');
  });

  it('空字典产出空串', () => {
    expect(buildSignPayload({})).toBe('');
  });

  it('/ 编码成 %2F', () => {
    expect(buildSignPayload({ u: 'a/b' })).toBe('u=a%2Fb');
  });

  it('空格编码成 %20 而非 +', () => {
    expect(buildSignPayload({ u: 'a b' })).toBe('u=a%20b');
    expect(buildSignPayload({ u: 'a b' })).not.toContain('+');
  });

  it("safe 集 -_.!~*'() 保持原样", () => {
    expect(buildSignPayload({ t: "-_.!~*'()" })).toBe("t=-_.!~*'()");
  });

  it('键本身也参与编码', () => {
    expect(buildSignPayload({ 'a b': 1 })).toBe('a%20b=1');
  });
});

describe('canonicalJson', () => {
  it('递归排序键', () => {
    expect(canonicalJson({ b: 1, a: { d: 2, c: 3 } })).toBe('{"a":{"c":3,"d":2},"b":1}');
  });

  it('数组保序', () => {
    expect(canonicalJson([3, 1, 2])).toBe('[3,1,2]');
  });

  it('数组内的对象仍排序', () => {
    expect(canonicalJson([{ b: 1, a: 2 }])).toBe('[{"a":2,"b":1}]');
  });

  it('紧凑分隔符，无空格', () => {
    expect(canonicalJson({ a: 1, b: 2 })).not.toContain(' ');
  });

  it('跳过 undefined 值，与 JSON.stringify 行为一致', () => {
    expect(canonicalJson({ a: 1, b: undefined })).toBe('{"a":1}');
  });

  it('保留 null', () => {
    expect(canonicalJson({ a: null })).toBe('{"a":null}');
  });
});

describe('generateNonce', () => {
  it('产出 32 位十六进制串', () => {
    expect(generateNonce()).toMatch(/^[0-9a-f]{32}$/);
  });

  it('连续调用不重复', () => {
    const seen = new Set(Array.from({ length: 200 }, () => generateNonce()));
    expect(seen.size).toBe(200);
  });
});
