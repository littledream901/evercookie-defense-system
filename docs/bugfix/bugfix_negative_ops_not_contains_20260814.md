# BugFix: not_contains 误判修复

**日期**: 2026-08-14  
**类型**: Bug修复  
**优先级**: 中（影响用户体验，但不影响功能正确性）  
**修复人**: Kiro AI Assistant

---

## 问题描述

规则编辑器中，当用户配置 **nullable 字段 + `not_contains` 操作符** 时，会错误地显示风险提示：

```
"IP 城市 可能为空，取值为空时此条件会命中。如需排除空值，请再加一条「IP 城市 不等于 空」"
```

### 实际行为

根据后端实现（`operators.py:102-112`）：

```python
def op_not_contains(actual: Any, expected: Any) -> bool:
    """包含取反。
    
    对不可能「包含」任何东西的实际值（None、数值、布尔）返回 False 而非 True。
    """
    if not isinstance(actual, str) and not _is_seq(actual):
        return False  # ⚠️ 空值时返回 False，不会命中
    return not op_contains(actual, expected)
```

**`not_contains(null, "test")` → `False`（不命中）**

### 对比其他否定操作符

```python
not_in(null, ["CN"])          → True  (命中，符合预期)
not_in_ci(null, ["CN"])       → True  (命中，符合预期)
neq(null, "CN")               → True  (命中，符合预期)
asn_not_in(null, [4134])      → True  (命中，符合预期)
cidr_list_not_in(null, [...]) → True  (命中，符合预期)
not_contains(null, "test")    → False (不命中，特殊处理)
```

### 根本原因

前端 `NEGATIVE_OPS` 集合错误地包含了 `not_contains`：

```typescript
// ❌ 修复前
export const NEGATIVE_OPS = new Set([
  'neq',
  'not_in',
  'not_in_ci',
  'not_contains',  // ⚠️ 不应该在这里
  'asn_not_in',
  'cidr_list_not_in'
])
```

导致风险提示逻辑误判：

```typescript
if (def.nullable && NEGATIVE_OPS.has(op)) {
  return `${def.label} 可能为空，取值为空时此条件会命中...`
}
```

---

## 修复方案

### 文件修改

**文件**: `dashboard-ui/src/constants/ruleFields.ts`

```diff
-/** 空值时会命中的否定类操作符，用于给 nullable 字段出风险提示 */
+/** 
+ * 空值时会命中的否定类操作符，用于给 nullable 字段出风险提示
+ * 
+ * not_contains 已排除：后端实现在空值时返回 False（不命中），
+ * 而非像其他否定操作符那样返回 True（命中）。
+ * 参见 operators.py:102-112 的特殊处理逻辑。
+ */
 export const NEGATIVE_OPS = new Set([
   'neq',
   'not_in',
   'not_in_ci',
-  'not_contains',
   'asn_not_in',
   'cidr_list_not_in'
 ])
```

---

## 测试验证

### 新增测试文件

**文件**: `tests/unit/test_negative_ops_risk_hint.py`

包含以下测试用例：

1. **test_negative_ops_match_on_null**  
   验证 NEGATIVE_OPS 中的操作符在空值时确实命中

2. **test_positive_ops_do_not_match_on_null**  
   验证正向操作符在空值时不命中

3. **test_not_contains_does_not_match_on_null**  
   专门验证 `not_contains` 在空值时不命中

4. **test_frontend_negative_ops_consistency**  
   **关键测试**：自动验证前端 NEGATIVE_OPS 定义与后端实际行为一致

5. **test_risk_hint_logic_examples**  
   模拟实际场景验证风险提示逻辑

### 测试结果

```bash
$ python -m pytest tests/unit/test_negative_ops_risk_hint.py -v

===================== 22 passed, 209 warnings in 0.21s =====================
```

✅ **所有测试通过**

---

## 影响范围

### 修复前的影响

- ❌ 用户配置 `ip.city not_contains "Beijing"` 时收到不必要的警告
- ❌ 用户可能误以为这是危险配置，实际上完全安全
- ❌ 降低了用户对风险提示系统的信任度

### 修复后的效果

- ✅ `not_contains` 不再触发误报警告
- ✅ 风险提示系统只对真正危险的配置发出警告
- ✅ 提高了用户对系统的信任度

### 不受影响的部分

- ✅ 后端逻辑完全未改动
- ✅ 其他操作符的风险提示不受影响
- ✅ 规则求值逻辑完全正确

---

## 为什么后端特殊处理 not_contains

**设计原因**（引用自 `operators.py:103-108`）：

> 对不可能「包含」任何东西的实际值（None、数值、布尔）返回 False 而非 True。
> 否则运营把该操作符用在数值/布尔字段上时条件恒成立，若处置是 deny
> 就等于对全部流量放开阻断。

### 举例说明

如果 `not_contains(null, "test")` 返回 `True`：

```yaml
# 假设运营误配置
条件: device.screen_width not_contains "1920"
处置: deny

# screen_width 是数值类型，永远不可能"包含"字符串
# 如果 not_contains 在数值上返回 True，此规则会拦截所有请求
```

通过返回 `False`，确保了操作符只在合理的场景下生效（字符串/列表字段）。

---

## 相关文档

- 操作符实现: `shared/src/fangyu_shared/rules/operators.py`
- 风险提示逻辑: `dashboard-ui/src/constants/ruleFields.ts:554-563`
- 操作符契约测试: `tests/gateway/test_rule_field_contract.py`
- 完整审计报告: 本对话历史记录

---

## 后续建议

### 自动化防护

建议在 CI/CD 中增加此测试：

```yaml
# .github/workflows/frontend-backend-contract.yml
- name: 验证前端 NEGATIVE_OPS 与后端行为一致
  run: python -m pytest tests/unit/test_negative_ops_risk_hint.py::test_frontend_negative_ops_consistency -v
```

### 文档完善

在规则编辑器文档中补充说明：

> **操作符特殊行为**：
> - `not_contains` 在空值时不命中（不会触发风险提示）
> - 其他否定操作符（`neq`, `not_in`, `not_in_ci` 等）在空值时会命中（需要风险提示）

---

## Checklist

- [x] 代码修改完成
- [x] 测试用例编写完成
- [x] 所有测试通过（22/22）
- [x] 注释清晰说明原因
- [x] 修复文档撰写完成
- [ ] 前端代码需要重新构建部署
- [ ] 用户文档更新（可选）

---

**修复状态**: ✅ 已完成  
**需要部署**: 是（前端代码变更）
