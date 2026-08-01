"""ClickHouse 参数化查询构建器。

设计目标：
- 强制参数绑定，杜绝拼接式 SQL 注入
- 字段名/表名走白名单校验，避免可控标识符注入
- 生成 aiochclient 可直接使用的 (sql, params) 元组
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Self

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

ComparisonOp = Literal["=", "!=", ">", ">=", "<", "<=", "LIKE", "NOT LIKE"]
LogicalOp = Literal["AND", "OR"]


def _validate_identifier(name: str, kind: str = "identifier") -> str:
    """校验标识符只包含字母、数字、下划线与点号，防止注入。"""
    if not isinstance(name, str) or not _IDENT_RE.fullmatch(name):
        raise ValueError(f"非法 {kind}: {name!r}")
    return name


@dataclass(frozen=True)
class QueryCondition:
    """单条 WHERE 条件。"""

    column: str
    op: ComparisonOp | Literal["IN", "NOT IN", "BETWEEN", "IS NULL", "IS NOT NULL"]
    value: Any = None

    def render(self, param_prefix: str, params: dict[str, Any]) -> str:
        col = _validate_identifier(self.column, "column")
        op = self.op

        if op in {"IS NULL", "IS NOT NULL"}:
            return f"{col} {op}"

        if op in {"IN", "NOT IN"}:
            if not isinstance(self.value, (list, tuple, set)):
                raise ValueError(f"{op} 需要 list/tuple/set，收到 {type(self.value).__name__}")
            values = list(self.value)
            if not values:
                # 空集合：IN => 恒假；NOT IN => 恒真
                return "0" if op == "IN" else "1"
            placeholders = []
            for idx, v in enumerate(values):
                key = f"{param_prefix}_{idx}"
                params[key] = v
                placeholders.append(f"%({key})s")
            return f"{col} {op} ({', '.join(placeholders)})"

        if op == "BETWEEN":
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                raise ValueError("BETWEEN 需要长度为 2 的 list/tuple")
            low_key = f"{param_prefix}_low"
            high_key = f"{param_prefix}_high"
            params[low_key] = self.value[0]
            params[high_key] = self.value[1]
            return f"{col} BETWEEN %({low_key})s AND %({high_key})s"

        if op not in {"=", "!=", ">", ">=", "<", "<=", "LIKE", "NOT LIKE"}:
            raise ValueError(f"不支持的操作符: {op}")

        params[param_prefix] = self.value
        return f"{col} {op} %({param_prefix})s"


class ClickHouseQueryBuilder:
    """安全的 SELECT 查询构建器。

    典型用法::

        sql, params = (
            ClickHouseQueryBuilder("decision_events")
            .select("app_id", "COUNT(*) AS total")
            .where("app_id", "=", 1)
            .where("created_at", "BETWEEN", (start, end))
            .group_by("app_id")
            .order_by("total", desc=True)
            .limit(100)
            .build()
        )
    """

    _AGG_RE = re.compile(
        r"^(?P<fn>COUNT|SUM|AVG|MIN|MAX|UNIQ|UNIQEXACT|QUANTILE)"
        r"\((?P<inner>\*|[A-Za-z_][A-Za-z0-9_.]*)\)"
        r"(?:\s+AS\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*))?$",
        re.IGNORECASE,
    )

    def __init__(self, table: str, *, database: str | None = None) -> None:
        self._table = _validate_identifier(table, "table")
        self._database = _validate_identifier(database, "database") if database else None
        self._columns: list[str] = []
        self._conditions: list[QueryCondition] = []
        self._group_by: list[str] = []
        self._order_by: list[str] = []
        self._having: list[QueryCondition] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._params: dict[str, Any] = {}
        self._logical_op: LogicalOp = "AND"

    def select(self, *columns: str) -> Self:
        """选择列。支持简单列名与受控的聚合表达式。"""
        for col in columns:
            if col == "*":
                self._columns.append("*")
                continue
            match = self._AGG_RE.match(col.strip())
            if match:
                fn = match.group("fn").upper()
                inner = match.group("inner")
                alias = match.group("alias")
                if inner != "*":
                    _validate_identifier(inner, "column")
                expr = f"{fn}({inner})"
                if alias:
                    _validate_identifier(alias, "alias")
                    expr = f"{expr} AS {alias}"
                self._columns.append(expr)
            else:
                self._columns.append(_validate_identifier(col, "column"))
        return self

    def where(self, column: str, op: str, value: Any = None) -> Self:
        self._conditions.append(QueryCondition(column=column, op=op, value=value))  # type: ignore[arg-type]
        return self

    def where_in(self, column: str, values: list[Any] | tuple[Any, ...]) -> Self:
        return self.where(column, "IN", list(values))

    def where_between(self, column: str, low: Any, high: Any) -> Self:
        return self.where(column, "BETWEEN", (low, high))

    def where_null(self, column: str) -> Self:
        return self.where(column, "IS NULL")

    def where_not_null(self, column: str) -> Self:
        return self.where(column, "IS NOT NULL")

    def logical(self, op: LogicalOp) -> Self:
        if op not in {"AND", "OR"}:
            raise ValueError(f"不支持的逻辑操作符: {op}")
        self._logical_op = op
        return self

    def group_by(self, *columns: str) -> Self:
        for col in columns:
            self._group_by.append(_validate_identifier(col, "column"))
        return self

    def order_by(self, column: str, *, desc: bool = False) -> Self:
        col = _validate_identifier(column, "column")
        self._order_by.append(f"{col} {'DESC' if desc else 'ASC'}")
        return self

    def having(self, column: str, op: str, value: Any = None) -> Self:
        self._having.append(QueryCondition(column=column, op=op, value=value))  # type: ignore[arg-type]
        return self

    def limit(self, n: int) -> Self:
        if n < 0:
            raise ValueError("limit 必须为非负整数")
        self._limit = int(n)
        return self

    def offset(self, n: int) -> Self:
        if n < 0:
            raise ValueError("offset 必须为非负整数")
        self._offset = int(n)
        return self

    def paginate(self, page: int, page_size: int) -> Self:
        if page < 1 or page_size < 1:
            raise ValueError("page 与 page_size 必须为正整数")
        return self.limit(page_size).offset((page - 1) * page_size)

    def build(self) -> tuple[str, dict[str, Any]]:
        """生成 (sql, params) 元组。"""
        self._params.clear()
        columns = ", ".join(self._columns) if self._columns else "*"
        full_table = f"{self._database}.{self._table}" if self._database else self._table
        sql_parts = [f"SELECT {columns}", f"FROM {full_table}"]

        if self._conditions:
            rendered = [
                cond.render(f"where_{i}", self._params) for i, cond in enumerate(self._conditions)
            ]
            sql_parts.append("WHERE " + f" {self._logical_op} ".join(rendered))

        if self._group_by:
            sql_parts.append("GROUP BY " + ", ".join(self._group_by))

        if self._having:
            rendered = [
                cond.render(f"having_{i}", self._params) for i, cond in enumerate(self._having)
            ]
            sql_parts.append("HAVING " + " AND ".join(rendered))

        if self._order_by:
            sql_parts.append("ORDER BY " + ", ".join(self._order_by))

        if self._limit is not None:
            sql_parts.append(f"LIMIT {self._limit}")
        if self._offset is not None:
            sql_parts.append(f"OFFSET {self._offset}")

        return "\n".join(sql_parts), dict(self._params)
