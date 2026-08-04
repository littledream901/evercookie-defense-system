# fangyu-shared

Evercookie Defense System V2 的跨服务共享库，供 gateway-api / admin-api / worker 三大服务及测试用例依赖。

## 包组成

| 子包 | 职责 |
|------|------|
| `fangyu_shared.event_normalizer` | 事件字段标准化 |
| `fangyu_shared.redis_manager` | Redis 连接池 |
| `fangyu_shared.clickhouse_manager` | ClickHouse 参数化查询 |
| `fangyu_shared.exceptions` | 统一业务异常与 FastAPI 处理器 |
| `fangyu_shared.logging` | 结构化日志 |
| `fangyu_shared.metrics` | Prometheus 指标封装 |
| `fangyu_shared.schemas` | 跨服务 Pydantic 模型 |
| `fangyu_shared.reputation` | 声誉聚合 SQL、评分公式与 ProfileCache 写回（worker 周期任务与 admin 手动触发共用） |
| `fangyu_shared.utils` | 通用工具（时间/加密/校验/异步） |

## 使用

```python
from fangyu_shared.event_normalizer import EventNormalizer
from fangyu_shared.redis_manager import RedisManager
from fangyu_shared.exceptions import ResourceNotFoundException
```
