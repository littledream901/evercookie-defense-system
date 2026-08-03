"""清理 0002 遗留的内置「默认应用」种子记录。

Revision ID: 20260803_0019
Revises: 20260803_0018
Create Date: 2026-08-03

0002 曾插入一条演示用应用，便于部署后立刻跑通 gateway 端到端链路。
该记录在 0010 重建 biz_application 后已退化为脏数据：
api_key / status / description / domains 四列均被 drop，site_id 被
回填成随机值，既不再携带弱 API Key，也不再有任何说明文案。

0002 已移除该 INSERT，但那只对未来的全新库生效；已部署环境里这条
记录仍在，需由本迁移清掉。

删除条件刻意收得很窄，避免误删用户真实创建的应用：
  1. name 必须等于种子名（含 APP_BOOTSTRAP_NAME 覆盖过的情况）
  2. 必须没有任何规则绑定（biz_rule_site 无引用）
  3. 必须没有页面资源配置
只要用户在这条记录上配过任何东西，就保留并交由人工处置。
"""
from __future__ import annotations

import os

import sqlalchemy as sa

from alembic import op

revision = "20260803_0019"
down_revision = "20260803_0018"
branch_labels = None
depends_on = None

# 与 0002 当时的取值保持一致：部署时若设过 APP_BOOTSTRAP_NAME，
# 种子记录用的就是那个名字。
_SEEDED_APP_NAME = os.getenv("APP_BOOTSTRAP_NAME", "默认应用")


def upgrade() -> None:
    conn = op.get_bind()

    row = conn.execute(
        sa.text("SELECT id FROM biz_application WHERE name = :n"),
        {"n": _SEEDED_APP_NAME},
    ).fetchone()

    if row is None:
        return

    app_id = row.id

    # 有规则绑定说明已被实际使用，不动。
    rule_refs = conn.execute(
        sa.text("SELECT COUNT(*) AS c FROM biz_rule_site WHERE site_id = :sid"),
        {"sid": app_id},
    ).scalar()
    if rule_refs:
        return

    # 注意 biz_page_resource 用的是 app_id，未随 0012 的 rule 表一起改名成 site_id。
    page_refs = conn.execute(
        sa.text("SELECT COUNT(*) AS c FROM biz_page_resource WHERE app_id = :sid"),
        {"sid": app_id},
    ).scalar()
    if page_refs:
        return

    conn.execute(
        sa.text("DELETE FROM biz_application WHERE id = :sid"),
        {"sid": app_id},
    )


def downgrade() -> None:
    # 演示数据不做恢复：重建一条没有 api_key、site_id 随机的空壳记录没有意义。
    pass
