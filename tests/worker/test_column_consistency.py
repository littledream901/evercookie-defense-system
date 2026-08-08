"""列一致性测试：解析 init.sql DDL 与 _to_ch_row 输出键对比。

目的：在 init.sql 添加新列或 _to_ch_row 新增字段后，任何不同步都会在此
测试里立刻暴露，而不是等到线上写入时收到 ClickHouse 类型不匹配错误。

排除列表：
- ingested_at：ClickHouse 服务端 DEFAULT now()，写入侧不传。
"""
from __future__ import annotations

import re
from pathlib import Path

from src.application.transformers.event_transformer import EventTransformer
from src.domain.event.stream_message import StreamMessage

_REPO_ROOT = Path(__file__).parents[2]
_INIT_SQL = _REPO_ROOT / "infrastructure" / "clickhouse" / "init.sql"

_SERVER_SIDE_COLUMNS = {"ingested_at"}

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS fangyu\.decision_events\s*\((.*?)\)\s*ENGINE",
    re.DOTALL | re.IGNORECASE,
)
_COLUMN_NAME_RE = re.compile(r"^\s{4}(\w+)\s+\S", re.MULTILINE)


def _parse_ddl_columns(sql: str) -> set[str]:
    match = _CREATE_TABLE_RE.search(sql)
    assert match, "未找到 fangyu.decision_events 的 CREATE TABLE 块"
    body = match.group(1)
    names = _COLUMN_NAME_RE.findall(body)
    return {n for n in names if n not in _SERVER_SIDE_COLUMNS}


def _ch_row_keys() -> set[str]:
    transformer = EventTransformer()
    msg = StreamMessage(
        stream="fangyu:events",
        message_id="0-0",
        payload={
            "eventId": "test",
            "siteId": 1,
            "fingerprint": "fp",
            "ip": "1.2.3.4",
            "occurredAt": "2026-07-31T00:00:00Z",
        },
    )
    result = transformer.transform([msg])
    assert result.rows, "transform 应生成至少一行"
    return set(result.rows[0].keys())


def test_ddl_columns_match_ch_row_keys():
    sql = _INIT_SQL.read_text(encoding="utf-8")
    ddl_cols = _parse_ddl_columns(sql)
    row_keys = _ch_row_keys()

    only_in_ddl = ddl_cols - row_keys
    only_in_row = row_keys - ddl_cols

    assert not only_in_ddl, (
        f"DDL 中有列但 _to_ch_row 未输出（漏写字段）: {sorted(only_in_ddl)}"
    )
    assert not only_in_row, (
        f"_to_ch_row 输出但 DDL 无对应列（多写字段）: {sorted(only_in_row)}"
    )
