# V2 分层架构说明（DDD）

**版本**: 2.0
**适用范围**: gateway-api / admin-api / worker

---

## 一、四层架构总览

```
┌────────────────────────────────────────────┐
│  interfaces/     接口适配层（HTTP / CLI）    │
├────────────────────────────────────────────┤
│  application/    应用层（用例编排、事务）      │
├────────────────────────────────────────────┤
│  domain/         领域层（核心业务规则）        │
├────────────────────────────────────────────┤
│  infrastructure/ 基础设施层（DB、Redis、外部）│
└────────────────────────────────────────────┘
```

**依赖方向**：`interfaces → application → domain ← infrastructure`
（domain 不依赖任何外部层，infrastructure 实现 domain 定义的接口）

---

## 二、各层职责

### 2.1 domain/（领域层）

**核心地位**：业务规则的唯一权威来源。

**内容**：
- **Entity（实体）**：有身份的业务对象，如 `Decision`、`Rule`、`User`
- **Value Object（值对象）**：无身份的不可变对象，如 `RiskScore`、`IPAddress`
- **Aggregate（聚合根）**：一致性边界，如 `RuleSet`、`AppConfig`
- **Domain Service（领域服务）**：跨实体的业务逻辑，如 `RiskCalculator`
- **Repository Interface（仓储接口）**：数据访问抽象（仅接口，不含实现）
- **Domain Event（领域事件）**：业务发生的事实

**规则**：
- ❌ 不导入 `infrastructure/`、`application/`、`interfaces/`
- ❌ 不依赖 FastAPI、SQLAlchemy、Redis 等外部框架
- ✅ 使用 Pydantic v2 或 `@dataclass` 定义模型
- ✅ 单测覆盖率 ≥ 95%

### 2.2 application/（应用层）

**核心地位**：编排用例，协调领域对象与基础设施。

**内容**：
- **Application Service（应用服务）**：编排用例流程，如 `DecisionService.decide()`
- **DTO（数据传输对象）**：跨层数据契约
- **Use Case（用例）**：粒度更细的操作单元（可选）

**规则**：
- ✅ 依赖 `domain/`（业务规则）
- ✅ 依赖 `infrastructure/` 中的接口（通过依赖注入）
- ❌ 不直接编写业务规则（应放到 domain）
- ❌ 不直接操作数据库（通过仓储接口）
- ✅ 处理事务边界

### 2.3 infrastructure/（基础设施层）

**核心地位**：技术实现，与外部世界打交道。

**内容**：
- **Repository Implementation（仓储实现）**：`AccessLogRepository`、`RuleRepository`
- **Cache（缓存）**：`DecisionCache`、`PermissionCache`
- **Message Bus（消息总线）**：`EventPublisher`、`StreamConsumer`
- **External Service Client**：`MMDBReader`、`ThreatIntelligenceClient`
- **DB Model（ORM 模型）**：SQLAlchemy 表定义

**规则**：
- ✅ 实现 `domain/` 定义的接口
- ✅ 与技术栈耦合（Redis、SQLAlchemy、ClickHouse 等）
- ❌ 不包含业务规则（业务应放到 domain）

### 2.4 interfaces/（接口适配层）

**核心地位**：适配外部输入（HTTP、CLI、消息队列等）。

**内容**：
- **HTTP Endpoint（HTTP 端点）**：FastAPI 路由
- **Middleware（中间件）**：Auth、RateLimit、Logging
- **Serializer（序列化器）**：请求 → DTO → 响应
- **CLI Command（命令行）**：Typer 命令

**规则**：
- ✅ 依赖 `application/`（调用应用服务）
- ❌ 不包含业务逻辑
- ✅ 处理认证、参数校验、错误映射

---

## 三、依赖注入示例

```python
# gateway-api/src/interfaces/http/dependencies.py
from fastapi import Depends
from src.application.services import DecisionService
from src.infrastructure.cache import RedisDecisionCache
from src.infrastructure.rule_repo import RedisRuleRepository

async def get_decision_service() -> DecisionService:
    return DecisionService(
        cache=RedisDecisionCache(),
        rule_repo=RedisRuleRepository(),
        profile_builder=ProfileBuilder(),
        precision_matcher=PrecisionMatcher(),
        security_checker=SecurityChecker(),
        risk_pipeline=RiskPipeline(),
        disposition_resolver=DispositionResolver(),
        event_publisher=RedisStreamPublisher(),
    )

# gateway-api/src/interfaces/http/v2/decide.py
@router.post("/v2/decide")
async def decide(
    body: DecideRequest,
    service: DecisionService = Depends(get_decision_service),
):
    decision = await service.decide(body)
    return decision.to_response()
```

---

## 四、领域事件驱动

```python
# domain/decision/events.py
@dataclass
class DecisionMadeEvent:
    request_id: str
    site_id: str
    device_id: str
    dispatch_type: str
    risk_score: int
    timestamp: int

# application/services/decision_service.py
class DecisionService:
    async def decide(self, request: DecideRequest) -> Decision:
        decision = ...  # 决策逻辑
        # 发布领域事件（异步）
        await self.event_publisher.publish(
            DecisionMadeEvent(
                request_id=decision.request_id,
                ...
            )
        )
        return decision
```

---

## 五、目录职责与代码规范

| 层 | 允许导入 | 禁止导入 | 单函数行数 | 覆盖率 |
|----|---------|---------|-----------|--------|
| domain | Python stdlib + Pydantic + shared/schemas | infrastructure、application、interfaces | ≤ 30 | ≥ 95% |
| application | domain + shared/* | interfaces | ≤ 50 | ≥ 85% |
| infrastructure | domain + shared/* + 外部库 | interfaces | ≤ 50 | ≥ 75% |
| interfaces | application + shared/* | domain 实体直接操作 | ≤ 30 | ≥ 70% |

---

## 六、反模式与规避

### ❌ 反模式 1：贫血领域模型
```python
# 反模式：领域模型只有属性没有行为
class Decision:
    request_id: str
    risk_score: int
    dispatch_type: str

# 业务规则都在应用服务中 —— 破坏封装
```

### ✅ 正确做法：充血领域模型
```python
class Decision:
    def __init__(self, ...): ...

    def is_high_risk(self) -> bool:
        return self.risk_score >= 80

    def should_block(self) -> bool:
        return self.is_high_risk() and self.dispatch_type == "high_risk"
```

### ❌ 反模式 2：跨层直接调用
```python
# 反模式：interfaces 直接使用 infrastructure
@router.post("/decide")
async def decide(body: DecideRequest):
    redis = await RedisManager.get_client()  # ❌
    ...
```

### ✅ 正确做法：通过应用服务
```python
@router.post("/decide")
async def decide(
    body: DecideRequest,
    service: DecisionService = Depends(get_decision_service),
):
    return await service.decide(body)
```

---

## 七、V1 vs V2 对比

| 维度 | V1（现状） | V2（目标） |
|------|-----------|-----------|
| 分层 | 扁平结构 | 4 层 DDD |
| 单文件行数 | 1000+ | ≤ 500 |
| 单函数行数 | 100+ | ≤ 50 |
| 业务规则位置 | 散落 | 集中在 domain |
| 数据访问 | 直接调用 | 仓储模式 |
| 依赖注入 | 全局单例 | FastAPI Depends |
| 测试性 | 难 | 易（依赖可替换） |
| 覆盖率 | ~ 45% | ≥ 80% |

---

**文档结束**
