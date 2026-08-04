"""声誉物化视图与查询侧的列名契约。

为什么需要这个测试
------------------
声誉回流链路是：``decision_events`` → MV（``init.sql``）→ 查询
（``fangyu_shared.reputation.aggregator``，worker 与 admin 共用）→ Redis
ProfileCache → ``IpReputationScorer``。

链路中的列名不一致**只在运行时暴露**，而且两侧的查询都包在 fail-open 里：
ClickHouse 报 `Unknown identifier` 后只记一条 warning，同步照常「成功」返回，
声誉分永久停在占位的 50.0。没有任何报警会指向真正的原因，最终表现为「风控
规则里的信誉分好像一直没生效」。

这里用静态解析把契约钉死：改了 MV 的列名，本文件立刻失败。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_INIT_SQL = _ROOT / "infrastructure" / "clickhouse" / "init.sql"
# 聚合 SQL 曾在 worker 与 admin 各存一份复制品，两侧都要单独校验。现在收口到
# shared 的唯一实现，本文件只需盯住这一个文件。
_QUERY = (
    _ROOT / "shared" / "src" / "fangyu_shared" / "reputation" / "aggregator.py"
)

_IP_MV = "mv_ip_reputation_daily"
_FP_MV = "mv_fingerprint_reputation_daily"

# 查询侧真正读取的列。MV 至少要提供这些。
_IP_REQUIRED = {"log_date", "ip", "total_count", "blocked_count"}
_FP_REQUIRED = {"log_date", "app_id", "fingerprint", "total_count", "blocked_count"}


def _sql_text() -> str:
    return _INIT_SQL.read_text(encoding="utf-8")


def _mv_body(name: str) -> str:
    """截取某个 MV 的 ``CREATE`` 到分号之间的正文。"""
    text = _sql_text()
    start = text.index(f"CREATE MATERIALIZED VIEW IF NOT EXISTS fangyu.{name}")
    end = text.index(";", start)
    return text[start:end]


def _selected_columns(name: str) -> set[str]:
    """解析 MV 的 SELECT 列表，取每个投影的输出名。

    只认 ``AS alias`` 与裸列名两种形式——MV 里没有更复杂的写法，刻意不写通用
    SQL 解析器：解析器出 bug 会让这个测试变成噪声来源。
    """
    body = _mv_body(name)
    select_part = body[body.index("AS SELECT") + len("AS SELECT") : body.index("FROM ")]
    columns: set[str] = set()
    for raw in select_part.split(","):
        piece = raw.strip()
        if not piece:
            continue
        match = re.search(r"\bAS\s+(\w+)\s*$", piece)
        columns.add(match.group(1) if match else piece)
    return columns


# ---------- MV 存在性 ----------
def test_init_sql_exists() -> None:
    assert _INIT_SQL.is_file(), f"缺少 {_INIT_SQL}"


@pytest.mark.parametrize("name", [_IP_MV, _FP_MV])
def test_mv_declared(name: str) -> None:
    assert f"fangyu.{name}" in _sql_text()


# ---------- 列名契约 ----------
def test_ip_mv_exposes_required_columns() -> None:
    missing = _IP_REQUIRED - _selected_columns(_IP_MV)
    assert not missing, f"{_IP_MV} 缺少查询侧需要的列: {sorted(missing)}"


def test_fingerprint_mv_exposes_required_columns() -> None:
    missing = _FP_REQUIRED - _selected_columns(_FP_MV)
    assert not missing, f"{_FP_MV} 缺少查询侧需要的列: {sorted(missing)}"


def test_queries_reference_declared_mvs() -> None:
    """查询里的表名必须是 init.sql 真的建了的那两个。"""
    source = _QUERY.read_text(encoding="utf-8")
    assert f"fangyu.{_IP_MV}" in source
    assert f"fangyu.{_FP_MV}" in source


def test_queries_only_use_declared_columns() -> None:
    """查询引用的聚合列必须都由 MV 提供。"""
    source = _QUERY.read_text(encoding="utf-8")
    declared = _selected_columns(_IP_MV) | _selected_columns(_FP_MV)
    for column in ("total_count", "blocked_count", "log_date"):
        if column in source:
            assert column in declared, f"{_QUERY.name} 引用了 MV 未提供的列 {column}"


# ---------- SummingMergeTree 的聚合要求 ----------
@pytest.mark.parametrize("name", [_IP_MV, _FP_MV])
def test_mv_uses_summing_merge_tree(name: str) -> None:
    assert "SummingMergeTree" in _mv_body(name)


def test_queries_sum_and_group_over_summing_merge_tree() -> None:
    """``SummingMergeTree`` 的行在合并前是多份，必须 ``sum()`` + ``GROUP BY``。

    直接 ``SELECT total_count`` 只会拿到某一个未合并分片的值，分数偏低且随
    后台合并进度漂移——这种错误不会报错，只会让分数看起来「不太对」。
    """
    source = _QUERY.read_text(encoding="utf-8")
    assert "sum(total_count)" in source
    assert "sum(blocked_count)" in source
    assert "GROUP BY" in source


def test_queries_filter_empty_keys() -> None:
    """空 ip / 空 fingerprint 不能成为画像键，否则会写出一条垃圾全局画像。"""
    source = _QUERY.read_text(encoding="utf-8")
    assert "ip != ''" in source
    assert "fingerprint != ''" in source


def test_queries_apply_min_samples_threshold() -> None:
    """必须有样本量门槛，否则一次访问就能把某个 IP 的信誉打到 0。"""
    source = _QUERY.read_text(encoding="utf-8")
    assert "HAVING" in source
    assert "min_samples" in source


def test_both_queries_group_by_app_id() -> None:
    """两个维度都必须按 app_id 分组。

    IP 侧曾经只 ``GROUP BY ip``：声誉分在所有租户间共享（一个站点的爬虫流量
    压低另一个站点对同一 IP 的评分），且用不上 MV 的主键前缀
    ``(log_date, app_id, ip)``，每小时全表扫一遍。指纹侧一直带 app_id，两者
    此前不一致。
    """
    source = _QUERY.read_text(encoding="utf-8")
    assert "GROUP BY app_id, ip" in source
    assert "GROUP BY app_id, fingerprint" in source


# ---------- 「已拦截」的口径 ----------
@pytest.mark.parametrize("name", [_IP_MV, _FP_MV])
def test_blocked_mechanisms_match_disposition_enum(name: str) -> None:
    """MV 里的「拦截」口径必须是真实存在的 mechanism 取值。

    写错一个字面量不会报错，只会让 ``blocked_count`` 恒为 0，所有 IP 的信誉
    分都变成满分 100——防护看起来正常，实际完全没有信誉输入。
    """
    from fangyu_shared.schemas.disposition import Mechanism

    body = _mv_body(name)
    match = re.search(r"mechanism IN \(([^)]*)\)", body)
    assert match, f"{name} 未见 mechanism 过滤"

    listed = {v.strip().strip("'") for v in match.group(1).split(",")}
    valid = {m.value for m in Mechanism}
    assert listed <= valid, f"{name} 引用了不存在的 mechanism: {sorted(listed - valid)}"


def test_blocked_definition_consistent_across_both_mvs() -> None:
    """两个 MV 的拦截口径必须一致，否则 IP 与设备的分数不可比。"""

    def _mechanisms(name: str) -> set[str]:
        match = re.search(r"mechanism IN \(([^)]*)\)", _mv_body(name))
        assert match
        return {v.strip().strip("'") for v in match.group(1).split(",")}

    assert _mechanisms(_IP_MV) == _mechanisms(_FP_MV)
