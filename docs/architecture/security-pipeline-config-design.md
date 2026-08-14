# 威胁情报与安全检查器可配置化设计方案

## 1. 问题背景

当前流水线中威胁情报和安全检查器使用**硬编码处置逻辑**：

### 现状问题

1. **威胁情报**（`decision_service.py:809-825`）
   - 命中威胁 IP 后固定返回 `deny()`
   - 无法配置处置动作（challenge/score）
   - 误报无法通过白名单绕过（因为威胁情报排在白名单之后）

2. **安全检查器**（`security.py:61-76`）
   - 扫描器检测固定返回 `deny()`
   - VPN+数据中心固定返回 `deny()`
   - 可能误杀合法用户（企业 VPN、渗透测试、开发环境）

3. **用户体验问题**
   - 前端无法显式配置处置策略
   - 违反"所有机制前端可配置"的设计原则
   - 运维无法灵活调整安全策略

---

## 2. 设计目标

### 核心原则
1. **完全可配置**：威胁情报/安全检查器的处置动作由前端配置
2. **分层处置**：支持 `deny`（直接拒绝）、`challenge`（人机验证）、`score`（加分项）
3. **向后兼容**：未配置时使用安全默认值（deny）
4. **性能优化**：配置缓存 30s，避免高频 DB 查询

---

## 3. 数据模型设计

### 3.1 数据库表：`biz_security_policy`

```sql
CREATE TABLE `biz_security_policy` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `site_id` INT NOT NULL,
  `enabled` BOOLEAN NOT NULL DEFAULT TRUE COMMENT '总开关',
  
  -- 威胁情报配置
  `threat_intel_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `threat_intel_action` VARCHAR(16) NOT NULL DEFAULT 'deny' COMMENT 'deny/challenge/score',
  `threat_intel_score` INT NOT NULL DEFAULT 100 COMMENT 'action=score 时的加分值',
  
  -- 安全扫描器配置
  `scanner_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `scanner_action` VARCHAR(16) NOT NULL DEFAULT 'deny',
  `scanner_score` INT NOT NULL DEFAULT 80,
  
  -- VPN+数据中心配置
  `vpn_datacenter_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `vpn_datacenter_action` VARCHAR(16) NOT NULL DEFAULT 'deny',
  `vpn_datacenter_score` INT NOT NULL DEFAULT 60,
  
  -- Tor 检测配置
  `tor_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `tor_action` VARCHAR(16) NOT NULL DEFAULT 'deny',
  `tor_score` INT NOT NULL DEFAULT 90,
  
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  UNIQUE KEY `uk_security_policy_site` (`site_id`),
  CONSTRAINT `fk_security_policy_site` FOREIGN KEY (`site_id`) REFERENCES `biz_site` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安全策略配置';
```

### 3.2 领域模型（Shared Schema）

```python
# shared/src/fangyu_shared/schemas/security.py

from pydantic import BaseModel, Field

class SecurityPolicyAction(str, Enum):
    """安全策略处置动作。"""
    DENY = "deny"          # 直接拒绝
    CHALLENGE = "challenge"  # 人机验证
    SCORE = "score"        # 加分项（不直接拦截）

class ThreatIntelPolicy(BaseModel):
    """威胁情报策略。"""
    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=100, ge=0, le=100)

class ScannerPolicy(BaseModel):
    """扫描器检测策略。"""
    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=80, ge=0, le=100)

class VpnDatacenterPolicy(BaseModel):
    """VPN+数据中心策略。"""
    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=60, ge=0, le=100)

class TorPolicy(BaseModel):
    """Tor 检测策略。"""
    enabled: bool = True
    action: SecurityPolicyAction = SecurityPolicyAction.DENY
    score: int = Field(default=90, ge=0, le=100)

class SecurityPolicy(BaseModel):
    """站点安全策略（完整配置）。"""
    site_id: int = Field(..., alias="siteId")
    enabled: bool = True
    threat_intel: ThreatIntelPolicy = Field(default_factory=ThreatIntelPolicy, alias="threatIntel")
    scanner: ScannerPolicy = Field(default_factory=ScannerPolicy)
    vpn_datacenter: VpnDatacenterPolicy = Field(default_factory=VpnDatacenterPolicy, alias="vpnDatacenter")
    tor: TorPolicy = Field(default_factory=TorPolicy)
```

---

## 4. Admin API 设计

### 4.1 路由定义

```python
# admin-api/src/interfaces/http/v2/security_policy.py

@router.get(
    "/sites/{site_id}/security-policy",
    response_model=SuccessResponse[SecurityPolicySchema | None],
)
async def get_security_policy(site_id: int, ...):
    """获取站点安全策略配置。"""
    pass

@router.put(
    "/sites/{site_id}/security-policy",
    response_model=SuccessResponse[SecurityPolicySchema],
)
async def upsert_security_policy(
    site_id: int,
    payload: SecurityPolicyUpsertRequest,
    ...
):
    """创建或更新站点安全策略。"""
    pass

@router.delete(
    "/sites/{site_id}/security-policy",
    status_code=204,
)
async def reset_security_policy(site_id: int, ...):
    """重置为默认策略（删除自定义配置）。"""
    pass
```

### 4.2 同步机制

```python
# admin-api/src/infrastructure/security_policy_sync.py

class SecurityPolicySync:
    """同步安全策略到 Redis。
    
    键格式：fangyu:security_policy:{site_id}
    TTL：1800s（30分钟）
    """
    
    async def sync(self, site_id: int, policy: SecurityPolicy) -> None:
        key = f"fangyu:security_policy:{site_id}"
        await self._redis.setex(
            key,
            1800,
            orjson.dumps(policy.model_dump(by_alias=True))
        )
```

---

## 5. Gateway 消费逻辑

### 5.1 缓存层

```python
# gateway-api/src/infrastructure/cache/security_policy_cache.py

class SecurityPolicyCache:
    """安全策略缓存（30分钟）。"""
    
    async def get(self, site_id: int) -> SecurityPolicy:
        key = f"fangyu:security_policy:{site_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return self._default_policy(site_id)
        return SecurityPolicy.model_validate(orjson.loads(raw))
    
    def _default_policy(self, site_id: int) -> SecurityPolicy:
        """未配置时返回安全默认值（全部 deny）。"""
        return SecurityPolicy(
            siteId=site_id,
            enabled=True,
            threatIntel=ThreatIntelPolicy(action=SecurityPolicyAction.DENY),
            scanner=ScannerPolicy(action=SecurityPolicyAction.DENY),
            vpnDatacenter=VpnDatacenterPolicy(action=SecurityPolicyAction.DENY),
            tor=TorPolicy(action=SecurityPolicyAction.DENY),
        )
```

### 5.2 决策服务改造

```python
# gateway-api/src/application/services/decision_service.py

async def _check_threat_intel(
    self,
    ctx: DecisionContext,
    policy: SecurityPolicy,  # 新增参数
) -> DispositionResolver | None:
    """威胁情报检查（可配置处置）。"""
    if not policy.threat_intel.enabled:
        return None
    
    ti = await ThreatIntelReader.check(str(ctx.ip))
    if not ti.is_threat:
        return None
    
    reason = f"threat_intel:{ti.category}"
    
    match policy.threat_intel.action:
        case SecurityPolicyAction.DENY:
            disposition = deny()
        case SecurityPolicyAction.CHALLENGE:
            disposition = challenge()
        case SecurityPolicyAction.SCORE:
            # 不直接拦截，返回 None 继续评分
            return None
    
    return DispositionResolver.from_threat_intel(disposition, reason=reason)

async def _check_security(
    self,
    ctx: DecisionContext,
    policy: SecurityPolicy,  # 新增参数
) -> tuple[SecurityCheckResult | None, float]:
    """安全检查（可配置处置）。
    
    返回：(直接拦截结果, 累积评分增量)
    """
    score_delta = 0.0
    
    # 1. 扫描器检查
    if policy.scanner.enabled and ctx.ua.crawler_category == "security":
        if policy.scanner.action == SecurityPolicyAction.DENY:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=deny(),
                    reason=f"security_scanner:{ctx.ua.crawler_vendor}",
                ),
                0.0,
            )
        elif policy.scanner.action == SecurityPolicyAction.CHALLENGE:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=challenge(),
                    reason=f"security_scanner:{ctx.ua.crawler_vendor}",
                ),
                0.0,
            )
        else:  # SCORE
            score_delta += policy.scanner.score
    
    # 2. VPN+数据中心检查
    if policy.vpn_datacenter.enabled and ctx.ip.is_vpn and ctx.ip.is_datacenter:
        if policy.vpn_datacenter.action == SecurityPolicyAction.DENY:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=deny(),
                    reason="vpn_on_datacenter",
                ),
                0.0,
            )
        elif policy.vpn_datacenter.action == SecurityPolicyAction.CHALLENGE:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=challenge(),
                    reason="vpn_on_datacenter",
                ),
                0.0,
            )
        else:  # SCORE
            score_delta += policy.vpn_datacenter.score
    
    # 3. Tor 检查
    if policy.tor.enabled and ctx.ip.is_tor:
        if policy.tor.action == SecurityPolicyAction.DENY:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=deny(),
                    reason="tor_exit_node",
                ),
                0.0,
            )
        elif policy.tor.action == SecurityPolicyAction.CHALLENGE:
            return (
                SecurityCheckResult(
                    triggered=True,
                    disposition=challenge(),
                    reason="tor_exit_node",
                ),
                0.0,
            )
        else:  # SCORE
            score_delta += policy.tor.score
    
    return (None, score_delta)
```

### 5.3 流水线调用改造

```python
# gateway-api/src/application/services/decision_service.py

async def decide(self, ctx: DecisionContext) -> DecisionResult:
    # ... 白名单、挑战通行、频控、缓存等阶段 ...
    
    # 加载安全策略
    security_policy = await self._security_policy_cache.get(ctx.site_id)
    
    # Stage: threat intel
    if security_policy.enabled and security_policy.threat_intel.enabled:
        ti_resolved = await self._check_threat_intel(ctx, security_policy)
        if ti_resolved:
            return self._finalize(ti_resolved, stages, score=100.0, shadow_hits=[])
    
    # Stage: security checks
    security_result, security_score_delta = await self._check_security(ctx, security_policy)
    if security_result and security_result.triggered:
        resolved = DispositionResolver.from_security(
            security_result.disposition,
            reason=security_result.reason,
        )
        return self._finalize(resolved, stages, score=100.0, shadow_hits=[])
    
    # Stage: risk scoring
    # 将 security_score_delta 加到评分中
    score_config = await self._scoring_config_cache.get(ctx.site_id)
    if score_config.enabled:
        risk_profile = await self._build_risk_profile(ctx)
        score = self._risk_pipeline.run(risk_profile, ...)
        score += security_score_delta  # 累加安全检查评分
        score = min(100.0, score)
        # ...
```

---

## 6. 迁移脚本

```python
# admin-api/alembic/versions/20260814_0005_security_policy.py

revision = '20260814_0005'
down_revision = '20260814_0004'

def upgrade() -> None:
    op.create_table(
        'biz_security_policy',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('threat_intel_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('threat_intel_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('threat_intel_score', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('scanner_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('scanner_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('scanner_score', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('vpn_datacenter_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('vpn_datacenter_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('vpn_datacenter_score', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('tor_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('tor_action', sa.String(length=16), nullable=False, server_default='deny'),
        sa.Column('tor_score', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', name='uk_security_policy_site'),
        sa.ForeignKeyConstraint(['site_id'], ['biz_site.id'], name='fk_security_policy_site', ondelete='CASCADE'),
        mysql_charset='utf8mb4',
        comment='安全策略配置'
    )

def downgrade() -> None:
    op.drop_table('biz_security_policy')
```

---

## 7. 测试策略

### 单元测试
- `test_security_policy_cache.py`：缓存加载、默认值
- `test_security_policy_service.py`：CRUD 操作
- `test_threat_intel_configurable.py`：威胁情报三种动作
- `test_scanner_configurable.py`：扫描器三种动作

### 集成测试
- 配置 `action=score` 时不直接拦截，加分到评分阶段
- 配置 `action=challenge` 时返回挑战页面
- 配置 `enabled=false` 时跳过检查

---

## 8. 前端交互

### API 端点
- `GET /api/v2/sites/{site_id}/security-policy` - 获取配置
- `PUT /api/v2/sites/{site_id}/security-policy` - 保存配置
- `DELETE /api/v2/sites/{site_id}/security-policy` - 重置默认

### 前端表单字段
```typescript
interface SecurityPolicyForm {
  enabled: boolean;
  threatIntel: {
    enabled: boolean;
    action: 'deny' | 'challenge' | 'score';
    score: number; // 0-100
  };
  scanner: {
    enabled: boolean;
    action: 'deny' | 'challenge' | 'score';
    score: number;
  };
  vpnDatacenter: {
    enabled: boolean;
    action: 'deny' | 'challenge' | 'score';
    score: number;
  };
  tor: {
    enabled: boolean;
    action: 'deny' | 'challenge' | 'score';
    score: number;
  };
}
```

---

## 9. 实施步骤

1. ✅ **设计文档** - 本文档
2. ⏳ **Shared Schema** - 定义 `SecurityPolicy` 领域模型
3. ⏳ **数据库迁移** - 创建 `biz_security_policy` 表
4. ⏳ **Admin API** - 实现 CRUD + 同步逻辑
5. ⏳ **Gateway 缓存** - 实现 `SecurityPolicyCache`
6. ⏳ **Gateway 决策** - 改造 `_check_threat_intel` 和 `_check_security`
7. ⏳ **测试验证** - 单元测试 + 集成测试
8. ⏳ **文档更新** - 更新用户手册和运维文档

---

## 10. 向后兼容性

- **未配置站点**：使用安全默认值（全部 `deny`），保持现有行为
- **Redis 缓存失效**：返回默认策略，不影响服务可用性
- **配置迁移**：现有站点无需手动迁移，自动使用默认值

---

## 11. 性能影响

- **Redis 查询**：+1 次 GET（30 分钟缓存）
- **决策延迟**：+0.5ms（反序列化 JSON）
- **内存占用**：每站点 ~1KB 配置数据
- **总体影响**：可忽略不计

---

## 12. 安全考虑

- **默认安全**：未配置时全部 `deny`，不放松安全策略
- **最小权限**：需要 `security.write` 权限才能修改
- **审计日志**：所有配置变更记录操作人和时间
- **灰度发布**：可按站点逐步启用 `action=score` 模式

---

## 附录：现有硬编码位置

### 威胁情报
- `gateway-api/src/application/services/decision_service.py:809-825`
- `gateway-api/src/infrastructure/threat_intel/reader.py`

### 安全检查器
- `gateway-api/src/domain/risk/security.py:61-76`
- `gateway-api/src/domain/risk/security.py:78-89` (Tor)
