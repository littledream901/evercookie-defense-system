"""Tests — ReputationWriter (worker) + ReputationSyncService (admin).

Exécution isolée (conftest worker isole sys.path) :
  python -m pytest tests/worker/test_reputation_writer.py -q
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fangyu_shared.reputation import calc_score as _calc_score
from fangyu_shared.schemas.profile import DeviceProfile, IpProfile
from src.application.writers.reputation_writer import (
    ReputationWriter,
    ReputationWriterConfig,
)

# ---------------------------------------------------------------------------
# _calc_score pure function
# ---------------------------------------------------------------------------

class TestCalcScore:
    """Contrat de score.

    La formule vit désormais dans ``fangyu_shared.reputation`` : les deux
    appelants (tâche périodique worker / déclenchement manuel admin) en
    partagent une seule implémentation, au lieu d'en dupliquer chacun une
    copie. Le même tableau de valeurs reste répliqué dans
    ``tests/admin/test_reputation_sync_service.py`` : si un jour quelqu'un
    recopie la formule dans l'un des deux services, l'un de ces fichiers
    échouera en premier.
    """

    def test_all_blocked_gives_zero(self):
        assert _calc_score(10, 10) == 0.0

    def test_none_blocked_gives_hundred(self):
        assert _calc_score(10, 0) == 100.0

    def test_half_blocked(self):
        assert _calc_score(10, 5) == 50.0

    def test_zero_total_returns_default_fifty(self):
        assert _calc_score(0, 0) == 50.0

    def test_blocked_exceeding_total_clamped(self):
        # Si données incohérentes (blocked > total), ne doit pas dépasser 0
        assert _calc_score(3, 10) == 0.0

    def test_result_rounded_two_decimals(self):
        score = _calc_score(3, 1)  # 1/3 bloqué → 100 - 33.33... = 66.67
        assert score == 66.67


# ---------------------------------------------------------------------------
# ReputationWriter.run_once
# ---------------------------------------------------------------------------

def _make_writer(ip_rows=None, device_rows=None):
    ch = MagicMock()
    ch.fetch = AsyncMock(side_effect=[
        ip_rows if ip_rows is not None else [],
        device_rows if device_rows is not None else [],
    ])
    redis = MagicMock()
    from fangyu_shared.cache.profile_cache import ProfileCache
    cache = MagicMock(spec=ProfileCache)
    cache._redis = redis
    cache.get_ip = AsyncMock(return_value=None)
    cache.set_ip = AsyncMock()
    cache.get_device = AsyncMock(return_value=None)
    cache.set_device = AsyncMock()
    writer = ReputationWriter(
        clickhouse=ch,
        profile_cache=cache,
        config=ReputationWriterConfig(min_samples=3),
    )
    return writer, cache


@pytest.mark.asyncio
async def test_ip_reputation_written_on_hit():
    writer, cache = _make_writer(
        ip_rows=[{"app_id": 7, "ip": "1.2.3.4", "total": 10, "blocked": 2}],
    )
    result = await writer.run_once()
    assert result.ips_written == 1
    assert result.errors == []
    cache.set_ip.assert_awaited_once()
    # set_ip(app_id, profile) — la clé de cache est scopée par locataire.
    app_id, written = cache.set_ip.call_args[0]
    assert app_id == 7
    assert isinstance(written, IpProfile)
    assert written.ip == "1.2.3.4"
    assert written.reputation_score == 80.0  # 100 - 20%
    assert written.reputation_samples == 10


@pytest.mark.asyncio
async def test_device_reputation_written_on_hit():
    writer, cache = _make_writer(
        device_rows=[{"app_id": 7, "fingerprint": "fp_abc", "total": 20, "blocked": 0}],
    )
    result = await writer.run_once()
    assert result.devices_written == 1
    cache.set_device.assert_awaited_once()
    written: DeviceProfile = cache.set_device.call_args[0][1]
    assert written.fingerprint == "fp_abc"
    assert written.reputation_score == 100.0
    assert written.blocked_requests == 0
    # last_seen_at doit être renseigné : les scorers basés sur l'âge du device
    # l'utilisent comme référence. L'équivalent admin
    # (ReputationSyncService) fait de même — les deux ne doivent pas diverger.
    assert written.last_seen_at is not None


@pytest.mark.asyncio
async def test_device_blocked_requests_persisted():
    """``blocked_requests`` doit être écrit, sinon la branche
    ``high_block_rate`` de ``DeviceScorer`` est du code mort.

    Le champ existe depuis toujours sur ``DeviceProfile`` mais aucun écrivain
    ne l'alimentait : il restait à 0, donc ``blocked_requests > 0`` était
    toujours faux et cette branche ne se déclenchait jamais.
    """
    writer, cache = _make_writer(
        device_rows=[{"app_id": 3, "fingerprint": "fp_bad", "total": 40, "blocked": 30}],
    )
    await writer.run_once()
    written: DeviceProfile = cache.set_device.call_args[0][1]
    assert written.blocked_requests == 30
    assert written.total_requests == 40
    # Le taux calculé par DeviceScorer doit dépasser son seuil de 0.5.
    assert written.blocked_requests / written.total_requests > 0.5


@pytest.mark.asyncio
async def test_merges_existing_ip_profile():
    existing = IpProfile(
        ip="5.6.7.8",
        country="US",
        reputation_score=50.0,
        reputation_samples=0,
        total_requests=5,
    )
    writer, cache = _make_writer(
        ip_rows=[{"app_id": 7, "ip": "5.6.7.8", "total": 15, "blocked": 15}],
    )
    cache.get_ip = AsyncMock(return_value=existing)

    result = await writer.run_once()
    assert result.ips_written == 1
    written: IpProfile = cache.set_ip.call_args[0][1]
    assert written.country == "US"          # geo data preserved
    assert written.reputation_score == 0.0  # fully blocked
    assert written.reputation_samples == 15


@pytest.mark.asyncio
async def test_ip_clickhouse_error_failopen():
    ch = MagicMock()
    ch.fetch = AsyncMock(side_effect=RuntimeError("CH down"))
    from fangyu_shared.cache.profile_cache import ProfileCache
    cache = MagicMock(spec=ProfileCache)
    cache._redis = MagicMock()
    writer = ReputationWriter(clickhouse=ch, profile_cache=cache,
                               config=ReputationWriterConfig())
    result = await writer.run_once()
    assert result.ips_written == 0
    assert len(result.errors) >= 1


@pytest.mark.asyncio
async def test_both_steps_run_when_ip_errors():
    """IP クエリが失敗してもデバイスは成功するべき。"""
    ch = MagicMock()
    ch.fetch = AsyncMock(side_effect=[
        RuntimeError("ip_ch_down"),
        [{"app_id": 1, "fingerprint": "fp", "total": 10, "blocked": 1}],
    ])
    from fangyu_shared.cache.profile_cache import ProfileCache
    cache = MagicMock(spec=ProfileCache)
    cache._redis = MagicMock()
    cache.get_device = AsyncMock(return_value=None)
    cache.set_device = AsyncMock()
    writer = ReputationWriter(clickhouse=ch, profile_cache=cache,
                               config=ReputationWriterConfig())
    result = await writer.run_once()
    assert result.devices_written == 1
    assert len(result.errors) >= 1  # IP 失败记录了错误


@pytest.mark.asyncio
async def test_empty_rows_writes_nothing():
    writer, cache = _make_writer(ip_rows=[], device_rows=[])
    result = await writer.run_once()
    assert result.ips_written == 0
    assert result.devices_written == 0
    cache.set_ip.assert_not_awaited()
    cache.set_device.assert_not_awaited()
