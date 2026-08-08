# 项目编码规范（AI 优化版）

**技术栈**：Python 3.11+ / FastAPI / Tortoise-ORM / Bash 4+  
**冲突优先级**：安全 > 正确性 > 性能 > 简洁性  
**例外条款**：违反规则时在代码上方注释 `# rule-exception: [规则编号] 原因: ...`，需经代码评审确认生效

---

## 1. 工作流规范（FLOW）

**[FLOW-001] MUST 读后改**  
- **触发条件**：修改任何业务代码、重构现有功能前  
- **强制要求**：必须先通读相关业务代码、注释、文档，充分理解原有设计意图、业务逻辑与边界场景  
- **禁止行为**：盲目修改、未理解设计就重构代码

**[FLOW-002] MUST 清理调试代码**  
- **触发条件**：代码提交前  
- **强制清理**：`print()`、`console.log/debug/info`、本地硬编码路径、测试占位代码  
- **允许保留**：`console.error/warn` 异常日志  
- **检查清单**：无残留调试代码、无 `/tmp` 文件提交、无硬编码敏感信息

**[FLOW-003] MUST Conventional Commits**  
- **格式要求**：`<type>: <description>`  
- **type 枚举**：`feat`(新功能) / `fix`(缺陷修复) / `refactor`(代码重构) / `docs`(文档更新) / `tests`(测试用例)

**[FLOW-004] SHOULD 前置校验**  
- **实现方式**：配置 pre-commit 钩子  
- **校验项**：禁止提交 `/tmp` 临时文件、无残留调试代码、无硬编码敏感信息

## 2. 目录与文件管理规范（DIR）

### 2.1 标准目录布局
```
项目根目录
├── .env.example          # 环境变量模板（长期、版本控制、唯一声明点）
├── .env                  # 本地真实配置（私有、禁止提交、.gitignore）
├── .gitignore            # 版本控制忽略规则
├── app/                  # 核心业务源码目录
├── config/               # 通用配置模板目录
│   └── *.example.yaml    # 配置示例文件
├── tests/                # 长期测试资产目录（版本控制）
│   ├── unit/             # 单元测试（工具函数、Service层）
│   ├── integration/      # 集成测试（接口、数据库联动）
│   └── fixtures/         # 全局测试固件、测试样例数据
├── docs/                 # 项目技术文档目录（版本控制）
│   ├── design/           # 架构/方案设计文档
│   ├── api/              # 接口说明文档
│   └── ops/              # 部署、运维、操作手册
├── scripts/              # 长期工程脚本（部署、初始化、清理）
└── tmp/                  # 本地临时文件统一目录（禁止提交）
    ├── .gitkeep          # 目录占位文件
    ├── scripts/          # 临时调试脚本、一次性处理脚本
    ├── data/             # 临时测试数据、导出文件、脱敏样本
    ├── logs/             # 本地开发运行日志
    ├── cache/            # 本地运行缓存、构建缓存
    └── reports/          # 测试覆盖率、性能分析报告
```

### 2.2 强制约束规则

**[DIR-001] MUST NOT 硬编码敏感信息**  
- **覆盖范围**：密钥、token、账号密码、第三方密钥  
- **强制要求**：统一从 `.env` 文件读取，禁止硬编码在代码中

**[DIR-002] MUST 配置文件权限**  
- **适用文件**：`.env` 及所有私有配置文件  
- **权限要求**：`chmod 600`，仅当前用户可读可写

**[DIR-003] MUST 长期文件归档规范**  
- **测试用例**：`/tests/{type}/test_{module}_{scene}.py`（提交入库）  
- **技术文档**：`/docs/{category}_{name}.md`（提交入库）  
- **配置模板**：`/.env.example`、`/config/*.example.yaml`（提交入库）

**[DIR-004] MUST 临时文件全域收敛**  
- **强制要求**：所有本地调试脚本、临时数据、运行日志、缓存、导出文件统一存放在 `/tmp/` 对应子目录  
- **禁止行为**：在项目根目录、源码目录、长期目录散落临时产物

**[DIR-005] MUST 临时文件生命周期**  
- **有效期**：默认 7 天，超期可自动清理  
- **升级规则**：复用 3 次及以上的临时脚本/数据，必须迁移至长期目录并纳入版本管控

**[DIR-006] MUST NOT 临时文件存敏感数据**  
- **禁止内容**：明文密钥、生产全量数据、用户隐私数据  
- **调试要求**：调试数据必须提前脱敏

**[DIR-007] MUST 同步更新 .gitignore**  
- **触发时机**：新增临时文件类型、私有配置、运行产物时  
- **强制要求**：同步更新 `.gitignore`，杜绝误提交

**[DIR-008] MUST 大文件管控**  
- **阈值**：单文件 > 100MB  
- **处理方式**：使用 Git LFS 或对象存储托管，禁止直接提交

**[DIR-009] MUST 文档同步更新**  
- **触发条件**：代码涉及架构、接口、流程、配置变更  
- **强制要求**：同步更新对应目录文档，保证文档与代码一致性

## 3. 架构设计规范（ARCH）

**[ARCH-001] MUST 分层架构**  
- **调用链**：`Controller → Service → DAO`  
- **禁止行为**：跳层调用、Controller 直接操作数据库

**[ARCH-002] SHOULD 方法行数约束**  
- **阈值**：单个业务方法 ≤ 50 行  
- **超阈处理**：长逻辑、多分支逻辑拆分为私有方法

**[ARCH-003] MUST NOT 魔法值**  
- **覆盖范围**：固定数字、字符串状态值、类型值  
- **强制要求**：提取为全局常量或枚举类管理

**[ARCH-004] MUST 资源主动释放**  
- **覆盖资源**：文件句柄、数据库连接、网络连接、缓存连接  
- **强制要求**：使用完毕显式调用 `close()`，避免资源泄露

**[ARCH-005] SHOULD 注释优先解释原因**  
- **适用场景**：复杂业务逻辑、特殊兼容处理、边界判断  
- **注释内容**：优先说明设计原因与业务背景，而非复述代码执行过程

## 4. ORM 与数据库规范（ORM）

* **[ORM-001] MUST NOT 原生 SQL 拼接**：杜绝 SQL 注入风险，全部通过 Tortoise-ORM 构建器实现
  ```python
  # ❌ 禁止
  await db.execute(f"SELECT * FROM users WHERE id={user_id}")
  # ✅ 正确
  await User.get(id=user_id)
  ```

* **[ORM-002] MUST 显式指定查询字段**：禁止 `SELECT *`，必须用 `.only()` / `.values()` 指定所需字段，减少 IO 与内存消耗
  ```python
  # ❌ 禁止
  users = await User.all()
  # ✅ 正确
  users = await User.all().only("id", "name")
  ```

* **[ORM-003] MUST 杜绍 N+1 查询**：循环内禁止执行独立查询，必须用 `prefetch_related` 预加载关联数据
  ```python
  # ❌ 禁止
  for user in users:
      profile = await Profile.get(user_id=user.id)
  # ✅ 正确
  users = await User.all().prefetch_related("profile")
  ```

* **[ORM-004] MUST 批量操作优化**：单次数据量 > 100 条时，禁止单条循环读写，必须用 `bulk_create` / `bulk_update`
* **[ORM-005] MUST 事务无阻塞 IO**：事务上下文内禁止 HTTP 请求、文件读写、远程调用，避免事务超时与锁占用过高
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

* **[ORM-006] MUST 数据库迁移管理**：表结构、字段、索引变更必须用 Aerich/Alembic 生成迁移文件，禁止手动改库、线上直接改表

## 5. 安全规范（SEC）

* **[SEC-001] MUST 外部入参校验**：所有接口外部参数必须通过 Pydantic 完成类型/范围/非空/格式校验，禁止直接使用原始入参
* **[SEC-002] MUST 租户数据隔离**：多租户业务所有 ORM 查/写/删操作必须强制携带 `tenant_id` 过滤，严格防止跨租户越权
  ```python
  # ❌ 禁止
  sites = await Site.all()
  # ✅ 正确
  sites = await Site.filter(tenant_id=request.state.tenant_id)
  ```

* **[SEC-003] MUST 上传文件安全校验**：三重校验——MIME 类型 + 文件头真实格式 + 文件大小限制

## 6. 异常与日志规范（ERR/LOG）

* **[ERR-001] MUST 统一错误码返回**：接口异常响应统一格式 `{"code": "ERR_XXX", "detail": "错误描述"}`
* **[ERR-002] MUST NOT 空吞异常**：捕获 ORM/业务/系统异常后必须转换为标准化业务错误抛出或返回，禁止空 `except` 静默吞异常
* **[LOG-001] MUST 日志敏感信息脱敏**：密码、token、密钥、手机号必须替换为 `***`，禁止明文打印
* **[LOG-002] SHOULD 全链路追踪**：接口全链路日志携带统一 `traceId`
* **[LOG-003] MUST 统一日志工具**：
* **[LOG-003] MUST 统一日志工具**：
  - Python 后端：使用 `logging.getLogger(__name__)` 而非 `print()`
  - Web 前端：使用 `@/utils/logger` 而非 `console.*`
  - Automation：使用 `src/utils/logger.js` 而非 `console.*`
* **[LOG-004] MUST NOT 前端普通控制台打印**：生产代码禁止 `console.log/debug/info`，仅保留 `console.error/warn`（vite 配置强制兜底）
* **[LOG-005] MUST 本地日志落盘规范**：本地开发日志统一输出至 `/tmp/logs/`，生产日志输出至系统日志/日志服务，禁止在源码目录生成日志文件
* **[LOG-006] SHOULD 日志文件轮转**：本地日志文件 > 50MB 自动轮转拆分，避免单文件过大

## 7. 高可用规范（HA）

* **[HA-001] MUST 缓存过期时间**：所有 Redis 缓存 Key 必须配置明确 TTL，禁止永久缓存，避免缓存堆积与脏数据残留
* **[HA-002] SHOULD 缓存三防策略**：核心业务实现防击穿（互斥锁）、防穿透（空值缓存）、防雪崩（随机偏移 TTL）
* **[HA-003] MUST 第三方请求超时**：所有 HTTP 第三方接口必须配置 `timeout`，默认 10s，杜绝无限阻塞
* **[HA-004] SHOULD 异步任务幂等**：所有异步队列任务、定时任务支持重试幂等性，重复执行不产生脏数据

## 8. 测试规范（TEST）

**[TEST-001] MUST 本地运行环境隔离**  
- **运行环境**：本地测试基于项目独立 `/.venv` 虚拟环境运行  
- **资源隔离**：所有测试资源（数据库、缓存、第三方依赖）使用本地资源，禁止依赖生产/线上环境

**[TEST-002] MUST Bug 回归用例划分**  
- **长期用例**：修复线上/测试 Bug 后，在 `/tests/{type}/` 新增长期回归用例并提交入库  
- **临时验证**：一次性调试验证脚本命名为 `verify_{bug_id}.py`，存放于 `/tmp/scripts/`，禁止提交

**[TEST-003] SHOULD 代码覆盖率指标**  
- **工具**：使用 `pytest-cov` 统计测试覆盖率  
- **目标**：项目整体业务代码覆盖率 ≥70%，核心 Service 业务逻辑覆盖率 ≥90%  
- **排除项**：部署脚本、启动入口、配置文件不计入考核

**[TEST-004] MUST 测试用例隔离**  
- **数据隔离**：每条测试用例使用独立 fixture、独立数据库事务，用例结束自动回滚  
- **禁止共享**：用例之间禁止共享可变内存、数据库状态、租户数据

**[TEST-005] SHOULD 标准化用例命名**  
- **格式**：`test_<功能>_<场景>_<预期结果>`  
- **示例**：`test_login_invalid_password_returns_401`

**[TEST-006] MUST 外部依赖 Mock**  
- **Mock 范围**：HTTP 接口、第三方服务、文件系统、缓存依赖  
- **工具**：使用 `pytest-mock` 模拟，保障测试离线可运行

**[TEST-007] MUST 测试资源自动清理**  
- **临时文件**：优先使用 `pytest tmp_path` fixture，测试结束自动销毁  
- **业务产物**：业务代码临时产物统一输出至 `/tmp`

**[TEST-008] MUST 测试目录分层落地**  
- **分层要求**：单元测试、集成测试、测试固件分类存放，禁止文件混杂堆放

**[TEST-009] MUST 测试租户隔离**  
- **强制要求**：所有数据库测试查询、写入操作强制绑定独立测试租户 ID，和线上租户逻辑一致

**[TEST-010] MUST 禁止测试代码硬编码**  
- **长期测试**：纳入版本控制的测试脚本禁止硬编码本机路径、账号、密钥  
- **临时调试**：临时硬编码调试逻辑仅允许写在 `/tmp` 临时脚本中

## 9. Shell 部署脚本规范（SH）

**[SH-001] MUST 严格运行模式**  
- **首行声明**：`#!/usr/bin/env bash`  
- **严格模式**：`set -euo pipefail`

**[SH-002] MUST 脚本绝对路径**  
- **获取方式**：`SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`  
- **禁止行为**：相对路径导致执行异常

**[SH-003] MUST 敏感参数环境读取**  
- **来源**：脚本所有敏感配置、账号密钥、环境参数统一从 `.env` 读取  
- **权限**：配置文件权限 `chmod 600`

**[SH-004] MUST 关键步骤错误处理**  
- **失败处理**：部署、初始化、清理等关键步骤执行失败后必须 `exit 1` 终止脚本  
- **避免问题**：防止异常执行导致脏数据、部署失败

**[SH-005] SHOULD 脚本幂等性**  
- **要求**：所有长期部署脚本支持幂等执行，重复运行不会覆盖、损坏已有线上数据与配置

**[SH-006] MUST 脚本分级存放**  
- **长期脚本**：部署、工具脚本存放于 `/scripts/` 并纳入版本控制  
- **临时脚本**：一次性调试 Shell 脚本仅允许存放于 `/tmp/scripts/`，禁止提交

---

## 代码示例

### ORM 禁止原生 SQL 拼接
```python
# ❌ 禁止
await db.execute(f"SELECT * FROM users WHERE id={user_id}")
# ✅ 正确
await User.get(id=user_id)
```

### ORM 显式字段查询
```python
# ❌ 禁止
users = await User.all()
# ✅ 正确
users = await User.all().only("id", "name")
```

### 杜绝 N+1 查询
```python
# ❌ 禁止
for user in users:
    profile = await Profile.get(user_id=user.id)
# ✅ 正确
users = await User.all().prefetch_related("profile")
```

### 事务无阻塞 IO
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

### 租户数据隔离
```python
# ❌ 禁止
sites = await Site.all()
# ✅ 正确
sites = await Site.filter(tenant_id=request.state.tenant_id)
```

### 前端日志规范
```typescript
// ❌ 禁止
console.log('用户登录', userId)
// ✅ 正确
import { logger } from '@/utils/logger'
logger.info('用户登录成功', { userId })
```
