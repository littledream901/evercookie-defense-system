# 站点流水线配置移至默认处置页面

## 1. 背景分析

### 当前架构问题

**现状**：
- 默认处置页面（`/sites/{site_id}/default-disposition`）只配置**最终兜底处置**
- 流水线各阶段的配置分散在多个地方：
  - 频控配置：`/sites/{site_id}/clock-limits`
  - 评分配置：`/sites/{site_id}/scoring-config`
  - 规则配置：`/sites/{site_id}/rules`
  - 白名单配置：`/sites/{site_id}/whitelist`
  - 威胁情报：硬编码（已提出可配置化方案）
  - 安全检查器：硬编码（已提出可配置化方案）

**问题**：
1. **配置分散**：用户需要在多个页面配置才能完整控制流水线
2. **缺乏全局视图**：看不到整个流水线的启用/禁用状态
3. **调试困难**：无法快速定位是哪个阶段拦截了流量
4. **命名混淆**："默认处置"听起来像"没有命中任何规则时的处置"，但实际是流水线最后一个阶段

---

## 2. 设计目标

### 核心理念
**将"默认处置"升级为"流水线配置中心"**：
- 统一管理所有流水线阶段的**启用/禁用开关**
- 保留各阶段详细配置的独立页面（频控、评分、规则等）
- 提供流水线执行顺序和阶段状态的可视化
- 保持默认处置的原有功能（最终兜底）

### 功能范围
1. **流水线全局开关**：一键启用/禁用整个风控系统
2. **分阶段开关**：独立控制每个阶段（白名单、频控、规则、评分、威胁情报等）
3. **执行顺序可视化**：清晰展示流水线执行流程
4. **快速跳转**：从流水线视图快速跳转到各阶段详细配置

---

## 3. 数据模型扩展

### 3.1 扩展 `biz_default_disposition` 表

**当前表结构**：
```sql
CREATE TABLE `biz_default_disposition` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `site_id` INT NOT NULL,
  `disposition` JSON NOT NULL COMMENT '默认处置（mechanism/target/challengeKind/ttlSeconds）',
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  UNIQUE KEY `uk_default_disposition_site` (`site_id`)
);
```

**新增字段**（迁移 20260814_0006）：
```sql
ALTER TABLE `biz_default_disposition`
  ADD COLUMN `pipeline_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '流水线总开关' AFTER `disposition`,
  ADD COLUMN `stage_whitelist_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '白名单阶段开关' AFTER `pipeline_enabled`,
  ADD COLUMN `stage_challenge_pass_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '挑战通行阶段开关' AFTER `stage_whitelist_enabled`,
  ADD COLUMN `stage_clock_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '频控阶段开关' AFTER `stage_challenge_pass_enabled`,
  ADD COLUMN `stage_rules_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '决策规则阶段开关' AFTER `stage_clock_enabled`,
  ADD COLUMN `stage_threat_intel_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '威胁情报阶段开关' AFTER `stage_rules_enabled`,
  ADD COLUMN `stage_security_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '安全检查阶段开关' AFTER `stage_threat_intel_enabled`,
  ADD COLUMN `stage_scoring_enabled` BOOLEAN NOT NULL DEFAULT TRUE 
    COMMENT '风险评分阶段开关' AFTER `stage_security_enabled`;
```

---

## 4. 领域模型更新

### 4.1 Shared Schema 扩展

```python
# shared/src/fangyu_shared/schemas/pipeline.py

from pydantic import BaseModel, Field

class PipelineStageConfig(BaseModel):
    """流水线阶段配置。"""
    whitelist: bool = Field(default=True, description="白名单阶段")
    challenge_pass: bool = Field(default=True, alias="challengePass", description="挑战通行阶段")
    clock: bool = Field(default=True, description="频控阶段")
    rules: bool = Field(default=True, description="决策规则阶段")
    threat_intel: bool = Field(default=True, alias="threatIntel", description="威胁情报阶段")
    security: bool = Field(default=True, description="安全检查阶段")
    scoring: bool = Field(default=True, description="风险评分阶段")

class PipelineConfig(BaseModel):
    """站点流水线配置（全局+分阶段开关）。"""
    site_id: int = Field(..., alias="siteId")
    enabled: bool = Field(default=True, description="流水线总开关")
    stages: PipelineStageConfig = Field(default_factory=PipelineStageConfig)
    default_disposition: Disposition | None = Field(default=None, alias="defaultDisposition")
```

---

## 5. Admin API 改造

### 5.1 路由重构

**现有路由**：
- `GET /sites/{site_id}/default-disposition` - 获取默认处置
- `PUT /sites/{site_id}/default-disposition` - 保存默认处置
- `DELETE /sites/{site_id}/default-disposition` - 重置默认处置

**新增路由**（保持向后兼容）：
```python
# admin-api/src/interfaces/http/v2/pipeline.py

@router.get(
    "/sites/{site_id}/pipeline-config",
    response_model=SuccessResponse[PipelineConfigSchema],
)
async def get_pipeline_config(site_id: int, ...):
    """获取站点流水线配置（包含阶段开关和默认处置）。"""
    pass

@router.put(
    "/sites/{site_id}/pipeline-config",
    response_model=SuccessResponse[PipelineConfigSchema],
)
async def update_pipeline_config(
    site_id: int,
    payload: PipelineConfigUpdateRequest,
    ...
):
    """更新流水线配置（总开关、分阶段开关、默认处置）。"""
    pass

@router.get(
    "/sites/{site_id}/pipeline-status",
    response_model=SuccessResponse[PipelineStatusResponse],
)
async def get_pipeline_status(site_id: int, ...):
    """获取流水线各阶段的实时状态（已配置规则数、频控窗口数等）。"""
    pass
```

### 5.2 DTO 设计

```python
# admin-api/src/interfaces/http/v2/schemas.py

class PipelineConfigSchema(BaseSchema):
    """流水线配置完整视图。"""
    site_id: int = Field(..., alias="siteId")
    enabled: bool = Field(default=True, description="流水线总开关")
    
    # 分阶段开关
    stage_whitelist: bool = Field(default=True, alias="stageWhitelist")
    stage_challenge_pass: bool = Field(default=True, alias="stageChallengePass")
    stage_clock: bool = Field(default=True, alias="stageClock")
    stage_rules: bool = Field(default=True, alias="stageRules")
    stage_threat_intel: bool = Field(default=True, alias="stageThreatIntel")
    stage_security: bool = Field(default=True, alias="stageSecurity")
    stage_scoring: bool = Field(default=True, alias="stageScoring")
    
    # 默认处置（保留原功能）
    default_disposition: DecisionDisposition | None = Field(default=None, alias="defaultDisposition")
    
    created_at: datetime
    updated_at: datetime

class PipelineConfigUpdateRequest(BaseSchema):
    """流水线配置更新请求。"""
    enabled: bool | None = None
    stage_whitelist: bool | None = Field(default=None, alias="stageWhitelist")
    stage_challenge_pass: bool | None = Field(default=None, alias="stageChallengePass")
    stage_clock: bool | None = Field(default=None, alias="stageClock")
    stage_rules: bool | None = Field(default=None, alias="stageRules")
    stage_threat_intel: bool | None = Field(default=None, alias="stageThreatIntel")
    stage_security: bool | None = Field(default=None, alias="stageSecurity")
    stage_scoring: bool | None = Field(default=None, alias="stageScoring")
    default_disposition: DecisionDisposition | None = Field(default=None, alias="defaultDisposition")

class PipelineStageStatus(BaseSchema):
    """单个阶段的状态信息。"""
    name: str
    enabled: bool
    order: int = Field(description="执行顺序，从1开始")
    has_config: bool = Field(description="是否已配置", alias="hasConfig")
    config_count: int = Field(default=0, description="配置项数量（规则数、白名单数等）", alias="configCount")
    description: str

class PipelineStatusResponse(BaseSchema):
    """流水线状态总览。"""
    site_id: int = Field(..., alias="siteId")
    pipeline_enabled: bool = Field(..., alias="pipelineEnabled")
    stages: list[PipelineStageStatus]
```

---

## 6. Gateway 消费逻辑

### 6.1 缓存层更新

```python
# gateway-api/src/infrastructure/cache/pipeline_config_cache.py

class PipelineConfigCache:
    """流水线配置缓存（30分钟）。
    
    键格式：fangyu:pipeline_config:{site_id}
    """
    
    async def get(self, site_id: int) -> PipelineConfig:
        key = f"fangyu:pipeline_config:{site_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return self._default_config(site_id)
        return PipelineConfig.model_validate(orjson.loads(raw))
    
    def _default_config(self, site_id: int) -> PipelineConfig:
        """未配置时返回全部启用。"""
        return PipelineConfig(
            siteId=site_id,
            enabled=True,
            stages=PipelineStageConfig(),
        )
```

### 6.2 决策服务改造

```python
# gateway-api/src/application/services/decision_service.py

async def decide(self, ctx: DecisionContext) -> DecisionResult:
    stages: list[str] = []
    shadow_hits: list[int] = []
    
    # 加载流水线配置
    pipeline_config = await self._pipeline_config_cache.get(ctx.site_id)
    
    # 流水线总开关关闭 → 直接放行
    if not pipeline_config.enabled:
        resolved = DispositionResolver.from_pipeline_disabled(allow())
        return self._finalize(resolved, ["pipeline_disabled"], score=0.0, shadow_hits=[])
    
    # Stage 1: whitelist（白名单优先级最高）
    if pipeline_config.stages.whitelist:
        wl_resolved = await self._check_whitelist(ctx)
        if wl_resolved:
            return self._finalize(wl_resolved, stages, score=0.0, shadow_hits=[])
    stages.append("whitelist")
    
    # Stage 2: challenge pass（挑战通行）
    if pipeline_config.stages.challenge_pass:
        cp_resolved = await self._check_challenge_pass(ctx)
        if cp_resolved:
            return self._finalize(cp_resolved, stages, score=0.0, shadow_hits=[])
    stages.append("challenge_pass")
    
    # Stage 3: clock（频控）
    if pipeline_config.stages.clock:
        limits = await self._clock_repo.get_limits(ctx.site_id)
        if limits.enabled:
            # ... 现有频控逻辑 ...
            pass
    stages.append("clock")
    
    # Stage 4: decision cache（缓存检查，不受开关控制）
    cached = await self._decision_cache.get(ctx.visitor_id, ctx.site_id)
    if cached:
        return self._finalize(cached, stages, score=cached.score, shadow_hits=[])
    stages.append("decision_cache")
    
    # 构建画像
    risk_profile = await self._build_risk_profile(ctx)
    
    # Stage 5: rules（决策规则）
    if pipeline_config.stages.rules:
        rule_set = await self._rule_repo.load(ctx.site_id)
        # ... 现有规则匹配逻辑 ...
        pass
    stages.append("rules")
    
    # Stage 6: threat intel（威胁情报）
    if pipeline_config.stages.threat_intel:
        ti_resolved = await self._check_threat_intel(ctx)
        if ti_resolved:
            return self._finalize(ti_resolved, stages, score=100.0, shadow_hits=[])
    stages.append("threat_intel")
    
    # Stage 7: security（安全检查）
    if pipeline_config.stages.security:
        sec_result = await self._check_security(ctx)
        if sec_result and sec_result.triggered:
            # ... 现有安全检查逻辑 ...
            pass
    stages.append("security")
    
    # Stage 8: scoring（风险评分）
    if pipeline_config.stages.scoring:
        score_config = await self._scoring_config_cache.get(ctx.site_id)
        if score_config.enabled:
            # ... 现有评分逻辑 ...
            pass
    stages.append("scoring")
    
    # Stage 9: default disposition（默认处置，始终生效）
    default_disp = await self._default_disposition_cache.get(ctx.site_id)
    resolved = DispositionResolver.from_default(default_disp or allow())
    return self._finalize(resolved, stages, score=score, shadow_hits=shadow_hits)
```

---

## 7. 同步机制

### 7.1 Admin 保存时同步

```python
# admin-api/src/infrastructure/pipeline_config_sync.py

class PipelineConfigSync:
    """同步流水线配置到 Redis。"""
    
    async def sync(self, site_id: int, config: PipelineConfig) -> None:
        key = f"fangyu:pipeline_config:{site_id}"
        await self._redis.setex(
            key,
            1800,  # 30分钟
            orjson.dumps(config.model_dump(by_alias=True))
        )
```

---

## 8. 前端交互

### 8.1 新增页面：流水线配置中心

**路由**：`/sites/{siteId}/pipeline`

**页面结构**：
```
┌─ 流水线配置中心 ─────────────────────────────┐
│                                            │
│ 🔧 流水线总开关：✅ 启用                    │
│                                            │
│ ┌─ 执行顺序 ──────────────────────────┐   │
│ │                                      │   │
│ │ 1️⃣ 白名单          ✅ 已配置 (15项)  │   │
│ │ 2️⃣ 挑战通行        ✅ 已启用          │   │
│ │ 3️⃣ 频控            ✅ 已配置 (3窗口)  │   │
│ │ 4️⃣ 决策缓存        ✅ 自动启用        │   │
│ │ 5️⃣ 决策规则        ✅ 已发布 (8条)   │   │
│ │ 6️⃣ 威胁情报        ✅ 已启用          │   │
│ │ 7️⃣ 安全检查器      ✅ 已启用          │   │
│ │ 8️⃣ 风险评分        ✅ 已配置          │   │
│ │ 9️⃣ 默认处置        ⚠️  未配置（放行）  │   │
│ │                                      │   │
│ └──────────────────────────────────────┘   │
│                                            │
│ [保存配置]                                 │
└────────────────────────────────────────────┘
```

### 8.2 API 调用流程

1. **加载配置**：`GET /api/v2/sites/{siteId}/pipeline-config`
2. **加载状态**：`GET /api/v2/sites/{siteId}/pipeline-status`
3. **更新配置**：`PUT /api/v2/sites/{siteId}/pipeline-config`

---

## 9. 迁移步骤

### 阶段1：数据库迁移（向后兼容）
1. 新增字段到 `biz_default_disposition` 表
2. 所有字段默认值为 `TRUE`（保持现有行为）

### 阶段2：Shared Schema 扩展
1. 新增 `PipelineConfig` / `PipelineStageConfig`
2. 扩展 `DefaultDisposition` 包含阶段开关

### 阶段3：Admin API 实现
1. 新增 `/sites/{site_id}/pipeline-config` 路由
2. 兼容保留 `/sites/{site_id}/default-disposition` 路由
3. 实现 `PipelineConfigSync` 同步到 Redis

### 阶段4：Gateway 消费
1. 新增 `PipelineConfigCache`
2. 改造 `DecisionService.decide()` 各阶段判断逻辑
3. 流水线总开关关闭时直接放行

### 阶段5：前端实现
1. 新增流水线配置中心页面
2. 保留各阶段详细配置页面（频控、评分、规则等）
3. 从流水线页面跳转到详细配置

---

## 10. 向后兼容性

### 10.1 数据库层
- 新字段均有默认值 `TRUE`，现有站点自动全部启用
- 旧 API 仍可使用，只读写 `disposition` 字段

### 10.2 API 层
- 保留 `/sites/{site_id}/default-disposition` 路由
- 新增 `/sites/{site_id}/pipeline-config` 路由
- 两套 API 操作同一张表，互不冲突

### 10.3 Gateway 层
- 未配置站点从 Redis 读不到配置时，返回"全部启用"默认值
- 流水线逻辑保持现有短路优先级

---

## 11. 测试策略

### 单元测试
- `test_pipeline_config_cache.py` - 缓存加载、默认值
- `test_pipeline_config_service.py` - CRUD 操作
- `test_pipeline_stage_switch.py` - 各阶段开关生效性

### 集成测试
- 流水线总开关关闭 → 所有流量放行
- 单个阶段关闭 → 跳过该阶段继续后续流水线
- 配置更新 30s 内生效

---

## 12. 命名变更建议

**当前名称**：默认处置（Default Disposition）
**新名称建议**：流水线配置中心（Pipeline Configuration Center）

**理由**：
- "默认处置"容易误解为"没命中规则时的处置"
- 实际功能已扩展为流水线全局配置+分阶段开关+兜底处置
- 新名称更准确反映功能定位

**URL 映射**：
- 旧：`/sites/{site_id}/default-disposition` → 保留向后兼容
- 新：`/sites/{site_id}/pipeline-config` → 推荐使用

---

## 13. 实施优先级

**P0（必须）**：
1. 数据库迁移新增字段
2. Shared Schema 扩展
3. Admin API CRUD 实现
4. Gateway 缓存层实现
5. Gateway 决策服务改造

**P1（重要）**：
1. 前端流水线配置中心页面
2. 流水线状态 API（显示各阶段配置项数量）
3. 测试覆盖

**P2（优化）**：
1. 流水线执行日志可视化
2. 阶段性能监控（各阶段耗时统计）
3. 流水线配置模板（快速套用常见场景）

---

## 附录：现有配置分散问题

### 当前需要配置的页面
1. 白名单：`/sites/{siteId}/whitelist`
2. 频控：`/sites/{siteId}/clock-limits`
3. 规则：`/sites/{siteId}/rules`
4. 评分：`/sites/{siteId}/scoring-config`
5. 默认处置：`/sites/{siteId}/default-disposition`

### 新架构下的统一入口
- 流水线中心：`/sites/{siteId}/pipeline` - 总览+开关
- 详细配置：各阶段独立页面（保留现有）
- 快速跳转：从流水线中心直接跳到详细配置
