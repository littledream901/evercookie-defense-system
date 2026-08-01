# V2 测试体系

## 目录结构

```
tests/
├── conftest.py           # 全局：仅注入 shared/src
├── shared/               # 与业务服务无关的纯 Python 测试
│   ├── test_shared_strings.py
│   └── test_shared_exceptions.py
├── admin/                # admin-api 领域层测试
│   ├── conftest.py       # 注入 admin-api，隔离 gateway/worker
│   ├── test_rbac_policy.py
│   └── test_rule_state_machine.py
└── gateway/              # gateway-api 领域层测试
    ├── conftest.py       # 注入 gateway-api，隔离 admin/worker
    └── test_gateway_disposition.py
```

## 分服务运行

由于 admin-api 与 gateway-api 都以 `src` 作为顶层包名，同一 pytest 进程内不能同时加载两者。请按服务分开运行：

```bash
make test-shared
make test-admin
make test-gateway
make test          # 顺序执行三者
```

或直接调用 pytest：

```bash
python -m pytest tests/shared -q
python -m pytest tests/admin -q
python -m pytest tests/gateway -q
```

## 集成 / 性能 / 安全测试

集成测试需要真实的 MySQL / Redis / ClickHouse，建议放在 `tests/integration/` 下，通过 pytest marker（如 `@pytest.mark.integration`）标记后按需触发。性能测试推荐使用 locust 或 k6 放在 `tests/perf/`。安全测试可用 bandit（静态）或 zap-baseline（动态）。

## 覆盖率

```bash
python -m pytest tests/shared tests/admin tests/gateway \
  --cov=shared/src/fangyu_shared \
  --cov=admin-api/src \
  --cov=gateway-api/src \
  --cov-report=term-missing
```
