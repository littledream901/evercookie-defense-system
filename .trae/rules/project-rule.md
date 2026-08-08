# rule.md
# 项目编码规范
**技术栈**：Python 3.11+ / FastAPI / Tortoise-ORM / Bash 4+  
**冲突优先级**：安全 > 正确性 > 性能 > 简洁性

---

## 1. 工作流
* **[FLOW-001] MUST 读后改**：修改前先读相关代码，理解设计意图
* **[FLOW-002] MUST 清理调试代码**：提交前删除 `print`/`console.*`（除 error/warn）/硬编码路径
* **[FLOW-003] MUST Conventional Commits**：提交消息格式 `feat:`/`fix:`/`refactor:`/`docs:`/`tests:`

## 2. 目录布局
```
/test/test_*.py         # 测试文件（MUST 以 test_ 开头）
/docs/                  # 文档
/.env.example           # 环境变量模板（MUST 唯一声明点）
/.env                   # 真实配置（MUST 在 .gitignore）
```
* **[DIR-001] MUST NOT 硬编码敏感信息**：密钥/token 必须从 `.env` 读取

## 3. 架构
* **[ARCH-001] MUST 分层**：`Controller → Service → DAO`，禁止越层
* **[ARCH-002] SHOULD 方法 ≤50 行**：长逻辑拆分私有方法
* **[ARCH-003] MUST NOT 魔法值**：数字/字符串常量提取为枚举/常量
* **[ARCH-004] MUST 资源释放**：文件句柄/连接池显式 `close()`
* **[ARCH-005] SHOULD 注释 Why**：复杂逻辑说明原因而非过程

## 4. ORM 与数据库
* **[ORM-001] MUST NOT 原生 SQL 拼接**：全部走 ORM 构建器
  ```python
  # ❌ 禁止
  await db.execute(f"SELECT * FROM users WHERE id={user_id}")
  # ✅ 正确
  await User.get(id=user_id)
  ```

* **[ORM-002] MUST 显式字段**：禁止 `SELECT *`，用 `.only()` 或 `.values()`
  ```python
  # ❌ 禁止
  users = await User.all()
  # ✅ 正确
  users = await User.all().only("id", "name")
  ```

* **[ORM-003] MUST NOT N+1**：循环中禁止单独查询
  ```python
  # ❌ 禁止
  for user in users:
      profile = await Profile.get(user_id=user.id)
  # ✅ 正确
  users = await User.all().prefetch_related("profile")
  ```

* **[ORM-004] MUST 批量操作**：`>100` 条记录用 `bulk_create` / `bulk_update`
* **[ORM-005] MUST NOT 事务中阻塞 I/O**：事务内禁止 HTTP/文件读写
  ```python
  # ❌ 禁止
  async with in_transaction():
      await user.save()
      await httpx.post("https://...")  # 阻塞事务
  # ✅ 正确
  async with in_transaction():
      await user.save()
  await httpx.post("https://...")
  ```

* **[ORM-006] MUST Migration**：表结构变更用 Aerich/Alembic 生成迁移文件

## 5. 安全
* **[SEC-001] MUST 入参校验**：外部请求参数做类型/范围/非空校验（Pydantic）
* **[SEC-002] MUST 租户隔离**：ORM 查询带 `tenant_id` 过滤，防越权
  ```python
  # ❌ 禁止
  sites = await Site.all()
  # ✅ 正确
  sites = await Site.filter(tenant_id=request.state.tenant_id)
  ```

* **[SEC-003] MUST 文件校验**：上传文件检查 MIME type + 文件头 + 大小限制

## 6. 异常与日志
* **[ERR-001] MUST 统一错误码**：接口返回 `{"code": "ERR_XXX", "detail": "..."}`
* **[ERR-002] MUST NOT 吞异常**：捕获 ORM 异常后转业务错误，禁止空 `except`
* **[LOG-001] MUST 脱敏**：日志中密码/token 用 `***` 替换
* **[LOG-002] SHOULD traceId**：全链路日志携带请求 ID
* **[LOG-003] MUST 统一日志工具**：
  - Python 后端：使用 `logging.getLogger(__name__)` 而非 `print()`
  - Web 前端：使用 `@/utils/logger` 而非 `console.*`
  - Automation：使用 `src/utils/logger.js` 而非 `console.*`
* **[LOG-004] MUST NOT 直接 console**：生产代码禁止使用 `console.log/debug/info`，仅允许 `console.error/warn`（已通过 vite 配置强制移除）
  ```typescript
  // ❌ 禁止
  console.log('用户登录', userId)
  // ✅ 正确
  import { logger } from '@/utils/logger'
  logger.info('用户登录成功', { userId })
  ```

## 7. 高可用
* **[HA-001] MUST 缓存 TTL**：Redis key 必须设过期时间
* **[HA-002] SHOULD 缓存三防**：防击穿（互斥锁）/穿透（空值缓存）/雪崩（随机 TTL）
* **[HA-003] MUST 第三方超时**：HTTP 请求设 `timeout`，默认 10s
* **[HA-004] SHOULD 幂等设计**：异步任务支持重试

## 8. 测试
* **[TEST-001] MUST 本地隔离**：测试在 Windows + `/.venv` 运行，不依赖生产环境
* **[TEST-002] MUST Bug 回归**：修 Bug 时在 `/tests` 补充用例,文件名 `test_bug_001.py` 等

## 9. Shell 脚本（部署用）
* **[SH-001] MUST 严格模式**：首行 `#!/usr/bin/env bash` + `set -euo pipefail`
* **[SH-002] MUST 绝对路径**：`SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`
* **[SH-003] MUST 环境变量**：敏感参数从 `.env` 读取，`chmod 600`
* **[SH-004] MUST 错误处理**：关键步骤失败后 `exit 1`
* **[SH-005] SHOULD 幂等**：重复执行不覆盖已有数据

---

**例外条款**：违反规则时在代码上方注释 `# rule-exception: [ORM-002] 原因: ...`
