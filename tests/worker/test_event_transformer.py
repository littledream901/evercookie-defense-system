"""Worker event_transformer 的幂等/版本号行为测试。"""
from __future__ import annotations

from datetime import datetime

from fangyu_shared.schemas.event import DECISION_EVENT_SCHEMA_VERSION
from src.application.transformers.event_transformer import EventTransformer, _to_count_map
from src.domain.event.stream_message import StreamMessage


def _msg(payload: dict, mid: str = "1-0") -> StreamMessage:
    return StreamMessage(stream="fangyu:events", message_id=mid, payload=payload)


def _base_payload(**overrides):
    payload = {
        "eventId": "evt-1",
        "appId": 42,
        "fingerprint": "fp-abc",
        "ip": "1.2.3.4",
        "action": "allow",
        "disposition": "ALLOW",
        "score": 12.5,
        "path": "/api",
        "occurredAt": "2026-07-31T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_transform_produces_versioned_row():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.invalid == []
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["event_id"] == "evt-1"
    assert row["app_id"] == 42
    assert row["schema_version"] == DECISION_EVENT_SCHEMA_VERSION
    # 未显式给 event_version 时用 occurred_at 毫秒填充，必须为正整数
    assert isinstance(row["event_version"], int)
    assert row["event_version"] > 0


def test_transform_uses_explicit_event_version_when_provided():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(eventVersion=987654321))])
    assert result.rows[0]["event_version"] == 987654321


def test_transform_drops_message_without_event_id():
    transformer = EventTransformer()
    payload = _base_payload()
    payload.pop("eventId")
    result = transformer.transform([_msg(payload)])
    assert result.rows == []
    assert len(result.invalid) == 1
    _mid, _payload, reason = result.invalid[0]
    assert "missing event_id" in reason


def test_transform_drops_message_with_invalid_app_id():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(appId=0))])
    assert result.rows == []
    assert result.invalid and "invalid app_id" in result.invalid[0][2]


def test_transform_falls_back_to_now_when_no_timestamp():
    transformer = EventTransformer()
    payload = _base_payload()
    payload.pop("occurredAt")
    before = datetime.utcnow()
    result = transformer.transform([_msg(payload)])
    row = result.rows[0]
    # event_version 兜底为 now 毫秒，肯定 >= before
    assert row["event_version"] >= int(before.timestamp() * 1000) - 1


def test_transform_handles_snake_case_aliases():
    transformer = EventTransformer()
    payload = {
        "event_id": "evt-snake",
        "app_id": 7,
        "fingerprint": "fp",
        "ip": "10.0.0.1",
        "user_agent": "UA/1.0",
        "device_id": "dev-1",
        "rule_ids": ["1", "2", "not-a-number"],
        "request_id": "req-1",
        "schema_version": 1,
        "event_version": 100,
    }
    result = transformer.transform([_msg(payload)])
    row = result.rows[0]
    assert row["event_id"] == "evt-snake"
    assert row["rule_ids"] == [1, 2]
    assert row["user_agent"] == "UA/1.0"
    assert row["device_id"] == "dev-1"
    assert row["request_id"] == "req-1"
    assert row["event_version"] == 100


def test_transform_partial_batch_reports_invalid_per_message():
    transformer = EventTransformer()
    ok = _msg(_base_payload(), mid="1-0")
    bad = _msg({"eventId": "", "appId": 42}, mid="1-1")
    result = transformer.transform([ok, bad])
    assert len(result.rows) == 1
    assert result.row_message_ids == ["1-0"]
    assert len(result.invalid) == 1
    assert result.invalid[0][0] == "1-1"


# ---------- _to_count_map 单元测试 ----------

def test_to_count_map_normal():
    assert _to_count_map({"w60s": 3, "w5m": 10}) == {"w60s": 3, "w5m": 10}


def test_to_count_map_negative_clipped_to_zero():
    result = _to_count_map({"w60s": -5, "w5m": 0})
    assert result["w60s"] == 0
    assert result["w5m"] == 0


def test_to_count_map_non_dict_returns_empty():
    assert _to_count_map(None) == {}
    assert _to_count_map([1, 2, 3]) == {}
    assert _to_count_map("bad") == {}


def test_to_count_map_empty_key_skipped():
    result = _to_count_map({"": 5, "ok": 2})
    assert "" not in result
    assert result["ok"] == 2


def test_to_count_map_key_truncated_to_32_chars():
    long_key = "x" * 50
    result = _to_count_map({long_key: 1})
    assert long_key not in result
    assert "x" * 32 in result


def test_to_count_map_non_numeric_value_skipped():
    result = _to_count_map({"w60s": "bad", "w5m": None, "ok": 7})
    assert "w60s" not in result
    assert "w5m" not in result
    assert result["ok"] == 7


# ---------- v3 字段集成测试 ----------

def test_ingress_defaults_to_sdk():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.rows[0]["ingress"] == "sdk"


def test_ingress_explicit_value():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(ingress="api"))])
    assert result.rows[0]["ingress"] == "api"


def test_ingress_snake_case_alias():
    transformer = EventTransformer()
    payload = _base_payload()
    payload.pop("occurredAt", None)
    payload["ingress"] = "edge"
    payload["occurredAt"] = "2026-07-31T10:00:00Z"
    result = transformer.transform([_msg(payload)])
    assert result.rows[0]["ingress"] == "edge"


def test_fingerprint_is_derived_false_by_default():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.rows[0]["fingerprint_is_derived"] == 0


def test_fingerprint_is_derived_true_camel():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(fingerprintIsDerived=True))])
    assert result.rows[0]["fingerprint_is_derived"] == 1


def test_fingerprint_is_derived_true_snake():
    transformer = EventTransformer()
    payload = _base_payload()
    payload["fingerprint_is_derived"] = True
    result = transformer.transform([_msg(payload)])
    assert result.rows[0]["fingerprint_is_derived"] == 1


def test_clock_banned_false_by_default():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.rows[0]["clock_banned"] == 0


def test_clock_banned_true():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(clockBanned=True))])
    assert result.rows[0]["clock_banned"] == 1


def test_clock_counts_populated():
    transformer = EventTransformer()
    counts = {"w60s": 3, "w5m": 12}
    result = transformer.transform([_msg(_base_payload(clockCounts=counts))])
    assert result.rows[0]["clock_counts"] == counts


def test_clock_counts_negative_clipped():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(clockCounts={"w60s": -1}))])
    assert result.rows[0]["clock_counts"]["w60s"] == 0


def test_clock_counts_absent_is_empty_dict():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.rows[0]["clock_counts"] == {}


def test_behavior_event_count_populated():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload(behaviorEventCount=5))])
    assert result.rows[0]["behavior_event_count"] == 5


def test_behavior_event_count_absent_is_zero():
    transformer = EventTransformer()
    result = transformer.transform([_msg(_base_payload())])
    assert result.rows[0]["behavior_event_count"] == 0
