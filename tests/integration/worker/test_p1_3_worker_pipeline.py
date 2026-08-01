"""P1-3：worker 读取决策事件并落 ClickHouse。"""
from __future__ import annotations

import orjson
import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.e2e]


async def test_worker_event_writer_persists_decision_event(worker_runtime: dict):
    from src.domain.event.stream_message import StreamMessage

    await worker_runtime["redis"].delete("fangyu:events:decision")
    await worker_runtime["redis"].delete("fangyu:events:decision:dlq")

    payload = {
        "eventId": "evt-p1-3-1",
        "appId": 9001,
        "fingerprint": "fp-worker-1",
        "deviceId": "dev-worker-1",
        "ip": "1.1.1.1",
        "ipType": "ipv4",
        "userAgent": "pytest-worker",
        "path": "/pay",
        "verdict": "hostile",
        "mechanism": "deny",
        "targetKind": "origin",
        "httpStatus": 403,
        "decidedBy": "decision_rule",
        "decidedStage": "decision_rule",
        "decidedRuleId": 77,
        "score": 88.5,
        "scorerScores": {"proxy": 40.0, "ua": 25.0},
        "ruleIds": [77],
        "reason": "rule:cn-block",
        "country": "CN",
        "asn": 4134,
        "connectionType": "datacenter",
        "deviceType": "desktop",
        "osName": "windows",
        "browserName": "chrome",
        "isBot": False,
        "requestId": "req-p1-3-worker",
        "occurredAt": "2026-07-31T10:00:00Z",
        "schemaVersion": 2,
        "eventVersion": 1780000000000,
        "extra": {},
    }

    message_id = await worker_runtime["redis"].xadd(
        "fangyu:events:decision",
        {"payload": orjson.dumps(payload).decode()},
    )

    outcome = await worker_runtime["writer"].handle(
        [StreamMessage(stream="fangyu:events:decision", message_id=message_id, payload=payload)]
    )
    assert outcome.dead_letter_count == 0
    assert outcome.ack_ids == [message_id]

    rows = await worker_runtime["clickhouse"].fetch(
        """
        SELECT event_id, app_id, fingerprint, verdict, mechanism, decided_by,
               country, asn, device_type, scorer_scores, request_id, score, rule_ids
        FROM fangyu.decision_events
        WHERE request_id = %(request_id)s
        ORDER BY occurred_at DESC
        LIMIT 1
        """,
        {"request_id": "req-p1-3-worker"},
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["event_id"] == "evt-p1-3-1"
    assert int(row["app_id"]) == 9001
    assert row["fingerprint"] == "fp-worker-1"
    assert row["verdict"] == "hostile"
    assert row["mechanism"] == "deny"
    assert row["decided_by"] == "decision_rule"
    assert row["request_id"] == "req-p1-3-worker"
    assert float(row["score"]) == 88.5
    assert list(row["rule_ids"]) == [77]
    # 解析结果必须落库，否则设备/地域维度分析无法进行
    assert row["country"] == "CN"
    assert int(row["asn"]) == 4134
    assert row["device_type"] == "desktop"
    assert dict(row["scorer_scores"])["proxy"] == pytest.approx(40.0)
