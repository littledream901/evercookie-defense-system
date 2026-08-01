# Evercookie Defense System V2

**版本**: 2.0.0
**状态**: 重写规划中
**目录用途**: V2 版本全新重写工作区，与根目录 V1 代码完全隔离

---

## 快速导航

- 📋 [完整重写计划](./docs/REWRITE_PLAN.md)
- 🏗️ [架构文档](./docs/architecture/)
- 📖 [API 文档](./docs/api/)
- 🧩 [模块文档](./docs/modules/)
- 🚀 [部署文档](./docs/deployment/)

---

## 项目结构

```
Evercookie Defense System V2/
├── shared/              # 跨服务共享包（8 个模块）
├── gateway-api/         # 决策引擎（DDD 分层）
├── admin-api/           # 管理后台（DDD 分层）
├── worker/              # 数据处理 Worker
├── dashboard-ui/        # Vue 3 + TS 前端
├── client-sdk/          # TypeScript SDK
├── adapters/            # 场景适配器（Nginx/Shopify/WordPress/Website）
├── infrastructure/      # 基础设施配置
├── tests/               # 集成/E2E/性能测试
├── docs/                # 文档
└── scripts/             # 辅助脚本
```

## 核心原则

1. **零耦合**：不导入 V1 代码，通过 API 契约保证兼容
2. **业务对齐**：V1 全部功能可迁移
3. **架构升级**：DDD + 分层架构 + 共享包
4. **测试先行**：核心模块覆盖率 ≥ 80%

## 六周实施节奏

| 周次 | 阶段 | 关键交付物 |
|------|------|-----------|
| W1 | 基础设施 + shared/ | 8 个共享包 |
| W2 | Gateway 引擎 | `/v2/decide` 可用 |
| W3 | Admin API | 后台完整功能 |
| W3-W4 | Worker | ETL 就绪 |
| W5 | 前端 + SDK | UI/SDK 就绪 |
| W6 | Adapters + 集成 | 生产就绪 |

## 性能目标

| 指标 | V1 | V2 目标 |
|------|----|----|
| P95 延迟 | 650ms | < 50ms |
| QPS | 1000 | ≥ 10000 |
| 缓存命中率 | 0% | ≥ 85% |

---

详细内容请查看 [REWRITE_PLAN.md](./docs/REWRITE_PLAN.md)
