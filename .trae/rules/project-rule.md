### AGENTS.md


# 冲突优先级: 安全 (SEC) > 正确性 (COR) > 性能 (PERF) > 简洁性 (SIMP)
# 例外条款: 违反规则需在上方标明 `# rule-exception: [规则编号] 原因: ...`

## 1. Mission & Overview
构建高安全、高可用且强规范的 FastAPI 接口服务。贯彻 Controller → Service → DAO 三层架构（严禁跨层调用），严格落实多租户隔离与全生命周期资源管理。

---

## 2. Directory Layout & Rules
- `app/`：业务源码（仅允许收敛生产代码）。
- `tests/`：长期测试资产（`unit/`, `integration/`, `fixtures/`）。
- `scripts/`：长期工程脚本（版本控制）。
- `/tmp/`：本地临时目录（日志 `/tmp/logs/`、单次调试脚本 `/tmp/scripts/`，严禁提交）。
- 配置规范：私有配置存 `.env`（`chmod 600`，不入库）；模板存 `.env.example`（入库）。

---

## 3. Tech Stack
Python 3.11+ | FastAPI (Async) | Tortoise-ORM | Pydantic v2 | Redis | Pytest | Bash 4+

---

## 4. Operating Rules (代码生成与评审准则)

### [FLOW & SEC] 工作流与安全
- **[FLOW-001] 读后改**：修改代码前必须先阅读现有业务逻辑与注释；提交遵循 Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `tests:`)。
- **[FLOW-002] 零调试残留**：严禁提交 `print()`、`console.log`、本地硬编码路径及 `/tmp` 临时文件。
- **[SEC-001/002] 零硬编码 & 租户隔离**：
  - 所有 Token/密钥统一自 `.env` 读取，接口入参强制经过 Pydantic 校验。
  - **强制过滤**：多租户查询/变更必须带有 `tenant_id=request.state.tenant_id`，杜绝越权。
- **[SEC-003] 文件上传**：校验 MIME 类型 + 文件头真实格式 + 文件大小。

### [ORM & ARCH] 数据库与架构
- **[ARCH-001/003] 架构与魔法值**：控制器不得直连 DB；无魔法值，常量/状态统一提取为 Enum；方法行数 ≤ 50 行。
- **[ORM-001/002] 杜绝 SQL 注入与全表检索**：
  - 严禁原生 SQL 拼接，完全采用 Tortoise-ORM 构建器。
  - 严禁 `SELECT *`，显式使用 `.only()` 或 `.values()`。
- **[ORM-003/004] 性能防护**：禁止循环内独立查询（统一用 `prefetch_related`）；单次处理 > 100 条必须用 `bulk_create` / `bulk_update`。
- **[ORM-005] 事务无阻塞 I/O**：`async with in_transaction():` 内**严格禁止**放置 HTTP 请求或文件 I/O。

### [ERR / LOG / HA] 异常、日志与高可用
- **[ERR-001/002] 标准响应**：异常统一返回 `{"code": "ERR_XXX", "detail": "..."}`；禁止裸露 `except:` 或空吞异常。
- **[LOG-001/003] 统一脱敏日志**：密码/Token 替换为 `***`；统一使用 `logging.getLogger(__name__)`，本地日志仅写往 `/tmp/logs/`。
- **[HA-001/003] 缓存与超时**：Redis 缓存必须配置 TTL；外部 HTTP 请求必须配置 `timeout`（默认 10s）。

### [SH] Shell 部署脚本
- **[SH-001/002] 严格执行**：首行 `#!\/usr\/bin\/env bash` + `set -euo pipefail`；获取绝对路径 `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`。

---

## 5. Standard Code Patterns (黄金标准代码范式)

### ORM 租户隔离 & 字段精简 & 预加载
```python
# ❌ BAD
users = await User.all()
for user in users:
    profile = await Profile.get(user_id=user.id)

# ✅ GOOD
users = (
    await User.filter(tenant_id=request.state.tenant_id)
    .only("id", "name", "email")
    .prefetch_related("profile")
)

```

### 事务中拆离异步 I/O

```python
# ❌ BAD
async with in_transaction():
    await user.save()
    await httpx.post("[https://api.example.com/notify](https://api.example.com/notify)")  # 阻塞事务

# ✅ GOOD
async with in_transaction():
    await user.save()
await httpx.post("[https://api.example.com/notify](https://api.example.com/notify)")  # 事务外执行网络 I/O

```

---

## 6. Debugging Order

1. **日志排查**：依据 `traceId` 追踪全链路日志，锁定 Controller / Service / ORM 故障层。
2. **环境隔离**：若需调试，在 `/tmp/scripts/` 下创建 `verify_{bug_id}.py` 编写隔离验证用例。
3. **ORM 审计**：检查是否缺失 `tenant_id`、未指定 `.only()`，或事务内存在阻塞 I/O。
4. **回归测试**：修复后在 `/tests/{type}/test_{module}_{scene}.py` 编写回归测试用例（核心 Service 覆盖率 ≥ 90%）。

---

## 7. Verification Checklist

* [ ] 代码无硬编码密钥，入参全过 Pydantic，私有配置为 `chmod 600`。
* [ ] 多租户查询均携带 `tenant_id`，ORM 检索显式声明 `.only()` / `.values()`。
* [ ] `async with in_transaction():` 块内无 HTTP/文件等阻塞 I/O。
* [ ] 提交代码中清除了 `print()`、临时变量及 `/tmp` 目录文件。
* [ ] Shell 脚本声明了 `set -euo pipefail` 且使用了 `SCRIPT_DIR` 绝对路径。
