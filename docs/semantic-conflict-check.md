# ⚠️ 语义冲突检查报告

## 发现的问题

### 当前架构理解
根据 `models.py`，V3 是**两层架构**：

```
Application (应用)
    ├── app_id: int (应用主键)
    ├── app_key: str (格式 app_<hex8>)
    └── sites: list[Site]
        └── Site (站点)
            ├── id: int (站点主键)
            ├── site_key: str (格式 site_<hex8>)
            └── app_id: int (外键 → Application.id)
```

### 语义冲突分析

#### ❌ **严重混淆**：在多处代码中，我们将 `site_id` 重命名后的字段实际指向的是**站点主键**，但在某些地方注释仍说"实际是站点主键"

让我检查具体的混淆点：

#### 1. **SiteModel 的 app_id 字段** ✅ 正确
```python
# admin-api/src/infrastructure/repositories/models.py:129
app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("biz_application.id"))
```
- **含义**：所属应用ID（外键）
- **用途**：站点归属于哪个应用
- **语义**：✅ 正确，这里 app_id 确实指向 Application

#### 2. **DecisionContext.site_id** ✅ 正确  
```python
# shared/src/fangyu_shared/schemas/decision.py:56
site_id: int = Field(default=0, alias="siteId", ge=0)
"""站点ID，由 gateway 根据 API Key 覆写，适配器无需填写。"""
```
- **含义**：站点主键（Site.id）
- **用途**：决策上下文中标识具体站点
- **语义**：✅ 正确

#### 3. **AppCredential.app_id** ⚠️ **这里有问题**
```python
# gateway-api/src/interfaces/http/middleware/app_key.py:70
@dataclass
class AppCredential:
    app_id: int  # 注释说"实际存储的是站点主键（Site.id）"
```

**问题**：
- Redis 键：`fangyu:app_keys:{site_key}` → `{"app_id": ???}`
- 注释说 `app_id` 存储的是**站点主键**
- 但 `site_key` 本身就是站点标识

**应该是**：
```python
# Redis 应该存储站点主键
fangyu:app_keys:{site_key} → {"site_id": <Site.id>, "site_secret": "..."}
```

#### 4. **ResolvedAppKey.site_id** ✅ 应该是站点主键
```python
# gateway-api/src/interfaces/http/middleware/app_key.py:92
@dataclass
class ResolvedAppKey:
    site_id: int  # 注释说"站点主键（Site.id）"
```
- **语义**：✅ 正确，这里应该是站点主键

---

## 🎯 核心问题总结

### 问题1：Redis 存储的字段名混淆
**当前状态**：
```python
# Admin API 写入 Redis
fangyu:app_keys:{site_key} → {"app_id": <WHAT?>}
```

**疑问**：这个 `app_id` 存的是什么？
- 如果是 `Site.id`（站点主键）→ 字段名应该改为 `site_id`
- 如果是 `Application.id`（应用主键）→ 那我们之前的重命名就错了

### 问题2：所有使用 `site_id` 的地方实际指向什么？
我们把很多地方的 `app_id` 改成了 `site_id`，但实际上：
- `DecisionContext.site_id` → 应该是 **Site.id**（站点主键）✅
- `ClockLimits.site_id` → 应该是 **Site.id**（站点主键）✅  
- `RuleBase.site_id` → 应该是 **Site.id**（站点主键）✅
- `credential.app_id` → 注释说是 **Site.id**，但字段名是 app_id ⚠️

---

## 📋 需要确认的问题

### 关键问题1：API Key 映射的是什么？

**X-App-Key（实际是site_key）映射到什么？**

选项A：映射到站点（Site）
```
X-App-Key: site_abc123
→ Redis查询 fangyu:app_keys:site_abc123
→ 返回 {"site_id": 1, "site_secret": "..."}
→ Gateway 知道这是站点 1
```

选项B：映射到应用（Application）
```
X-App-Key: site_abc123  
→ Redis查询 fangyu:app_keys:site_abc123
→ 返回 {"app_id": 10, "site_id": 1, "site_secret": "..."}
→ Gateway 同时知道应用 10 和站点 1
```

### 关键问题2：决策、规则、日志使用什么ID？

**当前所有重命名后的 `site_id` 用于**：
- 决策上下文
- 规则加载  
- ClickHouse 日志查询
- Redis 缓存键

**这个 ID 应该是**：
- `Site.id`（站点主键）→ 我们当前的重命名是正确的 ✅
- `Application.id`（应用主键）→ 我们的重命名全错了 ❌

---

## 🔍 建议的验证步骤

1. **检查 Admin API 如何写入 Redis**
   ```python
   # 查看写入 fangyu:app_keys:{key} 的代码
   # 确认写入的是什么ID
   ```

2. **检查 ClickHouse 日志表的实际数据**
   ```sql
   -- decision_events 表中存储的是什么ID？
   -- 是 Site.id 还是 Application.id？
   ```

3. **检查规则绑定逻辑**
   ```python
   # 规则绑定到站点还是应用？
   # biz_rule_site 关联表连接的是什么？
   ```

---

## 💡 我的判断

基于代码结构分析，我认为：

**✅ 当前重命名方向是正确的**：
- 所有决策、规则、日志都应该基于**站点级别**（Site.id）
- V3 架构中，Application 只是分组容器，实际业务都在 Site 层

**⚠️ 但需要修复的地方**：
1. `AppCredential.app_id` 应该改为 `site_id`（因为存的是站点ID）
2. Redis 键值中的 `app_id` 字段应该改为 `site_id`
3. 清理所有"app_id 实际是站点主键"的注释，直接用 site_id

---

**需要您确认**：
1. API Key（site_key）映射的是站点还是应用？
2. 决策、规则、日志应该基于站点还是应用？
