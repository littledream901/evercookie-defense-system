# Admin API 数据库迁移

## 目标

- 使用 Alembic 管理 admin-api 的 MySQL 元数据表结构。
- 与 SQLAlchemy 2.0 async 引擎完全兼容，同时兼容 CI/CD 里的同步驱动。

## 目录结构

```
admin-api/
├── alembic.ini                 # Alembic 主配置
└── alembic/
    ├── env.py                  # 运行时环境（读 AdminSettings，async 优先）
    ├── script.py.mako          # revision 模板
    ├── versions/               # 所有 revision 文件
    │   ├── 20260731_0001_initial_schema.py
    │   └── 20260731_0002_seed_default_data.py
    └── README.md
```

## 常用命令

```bash
cd admin-api

# 生成新迁移（自动 diff）
alembic revision --autogenerate -m "add xxx"

# 生成空迁移（数据种子/自定义 DDL）
alembic revision -m "seed default admin"

# 升级到最新
alembic upgrade head

# 回退一步
alembic downgrade -1

# 查看当前版本
alembic current

# 查看历史
alembic history
```

## 环境变量

- `ADMIN_DATABASE_URL` 或 `ALEMBIC_DATABASE_URL`：覆盖 `AdminSettings.database_url`。
- 若使用 CI 里的同步驱动（例如 `mysql+pymysql://`），env.py 自动切换到同步模式。

## 部署顺序

1. 建库：`CREATE DATABASE fangyu DEFAULT CHARACTER SET utf8mb4;`。
2. `alembic upgrade head` 建表 + 灌基础数据。
3. `python -m src.main` 启动 admin-api。

## 注意事项

- 每次修改 ORM 模型后必须新增 revision，禁止直接改历史文件。
- 数据类迁移（种子、数据修正）走独立 revision，与 DDL 迁移解耦。
- 生产环境执行 `upgrade` 前建议先 `--sql` 生成 SQL 审查。
