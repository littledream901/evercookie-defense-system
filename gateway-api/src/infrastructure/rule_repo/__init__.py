"""规则仓储：从 Redis 缓存 + 后端 API 拉取规则。"""

from __future__ import annotations

from src.infrastructure.rule_repo.rule_repository import RuleRepository

__all__ = ["RuleRepository"]
