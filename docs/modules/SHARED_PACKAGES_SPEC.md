# shared/ 共享包规范说明

**归属**: Evercookie Defense System V2 - Week 1 交付物
**范围**: 8 个共享包的详细接口设计

---

## 1. shared/event_normalizer

**目标**: 消除 admin-api 与 worker 之间事件标准化逻辑的重复实现。

### 1.1 文件清单

| 文件 | 职责 |
|------|------|
| `constants.py` | `DISPATCH_LABELS`、`IP_TYPE_LABELS` 常量表 |
| `types.py` | `NormalizedEvent` 类型定义（TypedDict / Pydantic） |
| `normalizer.py` | `EventNormalizer` 主类 |
| `__init__.py` | 对外导出 |

### 1.2 关键接口

```python
class EventNormalizer:
    @staticmethod
    def normalize_timestamp_ms(value: Any) -> int | None: ...
    @staticmethod
    def normalize_dispatch_type(value: Any) -> str: ...
    @staticmethod
    def normalize_ip_type(value: Any) -> str: ...
    @staticmethod
    def normalize_url(value: Any) -> str | None: ...
    @staticmethod
    def normalize_ua(value: Any) -> str | None: ...
    @classmethod
    def normalize(cls, entry: dict) -> NormalizedEvent: ...
```

### 1.3 测试点

- 秒 / 毫秒 / 微秒时间戳自动识别
- None、空字符串、非法字符串安全返回 `None`
- 中文标签映射一致性
- 与 V1 输出对齐（10 万条样本 diff）

---

## 2. shared/redis_manager

**目标**: 全局 Redis 连接池单例，供所有服务复用。

### 2.1 关键接口

```python
class RedisManager:
    @classmethod
    async def init(cls, url: str, max_connections: int = 100, socket_timeout: float = 5.0) -> None: ...
    @classmethod
    async def get_client(cls) -> Redis: ...
    @classmethod
    async def close(cls) -> None: ...
    @classmethod
    def is_initialized(cls) -> bool: ...
```

### 2.2 配置建议

- `max_connections`：Gateway 100 / Admin 50 / Worker 30
- `socket_timeout`：5s
- `socket_connect_timeout`：2s
- `retry_on_timeout`：True
- `decode_responses`：True

---

## 3. shared/clickhouse_manager

**目标**: 提供参数化查询构建器，消除 SQL 注入风险。

### 3.1 关键接口

```python
class ClickHouseQueryBuilder:
    def __init__(self, table: str) -> None: ...
    def select(self, *columns: str) -> "ClickHouseQueryBuilder": ...
    def where(self, condition: str, **params: Any) -> "ClickHouseQueryBuilder": ...
    def order_by(self, column: str, desc: bool = False) -> "ClickHouseQueryBuilder": ...
    def group_by(self, *columns: str) -> "ClickHouseQueryBuilder": ...
    def limit(self, n: int) -> "ClickHouseQueryBuilder": ...
    def offset(self, n: int) -> "ClickHouseQueryBuilder": ...
    def build(self) -> tuple[str, dict[str, Any]]: ...
```

### 3.2 客户端

```python
class ClickHouseClient:
    async def execute(self, query: str, params: dict) -> list[dict]: ...
    async def execute_many(self, query: str, params_list: list[dict]) -> None: ...
    async def insert_batch(self, table: str, rows: list[dict]) -> int: ...
```

---

## 4. shared/exceptions

**目标**: 统一业务异常体系与 HTTP 响应格式。

### 4.1 异常层次

```
BusinessException (基类)
├── ResourceNotFoundException     # 404
├── PermissionDeniedException     # 403
├── ValidationException           # 422
├── AuthenticationException       # 401
├── ConflictException             # 409
├── RateLimitException            # 429
└── ExternalServiceException      # 502
```

### 4.2 FastAPI 处理器

```python
def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BusinessException)
    async def business_exception_handler(request: Request, exc: BusinessException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request.state.request_id,
            },
        )
```

---

## 5. shared/logging

**目标**: 结构化日志（JSON），支持请求上下文追踪。

### 5.1 关键接口

```python
def configure_logging(service_name: str, level: str = "INFO", json_format: bool = True) -> None: ...
def get_logger(name: str) -> structlog.BoundLogger: ...

class RequestContextMiddleware:
    """注入 request_id、user_id 到日志上下文"""
```

### 5.2 日志字段

- `timestamp`：ISO 8601
- `level`：DEBUG/INFO/WARNING/ERROR/CRITICAL
- `service`：gateway-api / admin-api / worker
- `logger`：模块名
- `request_id`：链路追踪 ID
- `user_id`：可选
- `message`：事件描述
- `context`：任意结构化字段

---

## 6. shared/metrics

**目标**: Prometheus 指标封装 + 装饰器。

### 6.1 内置指标

```python
# 计数器
request_total = Counter("request_total", "HTTP requests", ["service", "endpoint", "status"])
error_total = Counter("error_total", "Error count", ["service", "error_type"])

# 直方图
request_latency = Histogram("request_latency_seconds", "Request latency", ["service", "endpoint"])

# 计量
cache_hit_rate = Gauge("cache_hit_rate", "Cache hit rate", ["cache_type"])
active_connections = Gauge("active_connections", "Active connections", ["service"])
```

### 6.2 装饰器

```python
@track_latency("decision_service", "decide")
@track_errors("decision_service")
async def decide(request: DecideRequest) -> Decision: ...
```

---

## 7. shared/schemas

**目标**: 跨服务共享 Pydantic v2 模型（DTO / VO）。

### 7.1 主要 Schema

| 文件 | 内容 |
|------|------|
| `event.py` | `AccessEvent`、`DecisionEvent`、`NormalizedEvent` |
| `decision.py` | `DecideRequest`、`DecideResponse`、`Disposition` |
| `profile.py` | `DeviceProfile`、`NetworkProfile`、`GeoProfile` |
| `rule.py` | `Rule`、`RuleCondition`、`RuleAction` |
| `common.py` | `Pagination`、`ApiResponse`、`RequestMeta` |

---

## 8. shared/utils

**目标**: 通用工具函数。

### 8.1 模块清单

| 文件 | 内容 |
|------|------|
| `crypto.py` | HMAC-SHA256 签名、AES-GCM 加密 |
| `time.py` | 时间戳转换、时区处理 |
| `validators.py` | IP、UA、URL、Email 校验 |
| `strings.py` | 字符串标准化、脱敏 |
| `async_utils.py` | `run_with_timeout`、`gather_with_concurrency` |

---

## 目录初始化脚本

```bash
cd "e:\Python\evercookie-defense-system\Evercookie Defense System V2\shared"

for pkg in event_normalizer redis_manager clickhouse_manager exceptions logging metrics schemas utils; do
  mkdir -p $pkg
  touch $pkg/__init__.py
done
```

---

## 单测要求（Week 1 验收）

| 包 | 覆盖率目标 |
|------|-----------|
| event_normalizer | ≥ 95% |
| redis_manager | ≥ 90% |
| clickhouse_manager | ≥ 90% |
| exceptions | ≥ 95% |
| logging | ≥ 85% |
| metrics | ≥ 85% |
| schemas | ≥ 95% |
| utils | ≥ 95% |

**整体 shared/ 覆盖率 ≥ 92%**
