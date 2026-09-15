"""
tests.test_spool
================
BUF-1: local delivery buffer (probe/spool.py), its wiring into
scripts/live_emit.py and probe/sdk.py, and the gateway duplicate guard
that makes re-sending safe.

Contract
--------
Input: a signed SignalBatch whose delivery failed (no status, or 5xx).
Output: the exact signed bytes on disk; re-sent first on the next run;
removed on 202 or 409.
Invariants: only signed canonical SignalBatch bytes are stored; writes
are atomic; entries expire after 30 h; the spool is capped; a 4xx other
than 409 is never retried; the gateway ingests a batch_id once.

Adversarial cases
-----------------
(a) Sybil / tampered spool file: bytes changed after signing -> gateway
    401 -> quarantined, never re-sent.  A file that no longer parses is
    quarantined without being sent at all.
(b) Replay: the same signed batch sent twice -> 409, CUSUM sees it once.
(c) Silent provider shift: the spool never alters metric values; what
    the gateway stores is byte-for-byte what the probe signed.

#SG-TRACE: REQ-BUF-001
#   | test: test_duplicate_batch_id_returns_409_and_skips_cusum
#SG-TRACE: REQ-BUF-002 | test: test_put_then_drain_delivers_exact_signed_bytes
#SG-TRACE: REQ-BUF-003 | test: test_put_refuses_body_with_raw_text_field
#SG-TRACE: REQ-BUF-004 | test: test_drain_treats_409_as_delivered
#SG-TRACE: REQ-BUF-005
#   | test: test_tampered_spool_file_is_quarantined_not_resent
#SG-TRACE: REQ-BUF-006 | test: test_post_status_returns_http_error_code
#SG-TRACE: REQ-BUF-007 | test: test_deliver_spools_on_transport_error
#SG-TRACE: REQ-BUF-008 | test: test_main_drains_spool_before_probing
#SG-TRACE: REQ-BUF-009 | test: test_flush_drains_spool_before_new_batches
#SG-TRACE: REQ-BUF-010 | test: test_flush_spools_on_503_and_continues
"""

from __future__ import annotations

import base64
import io
import json
import random
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from engine.clickhouse import ClickHouseRepository
from fastapi.testclient import TestClient
from gateway.main import app
from probe.canary import execute_canary
from probe.crypto import KeyManager, canonical_json
from probe.providers import ProviderError
from probe.sdk import ProbeConfig, ProbeSDK
from probe.spool import Spool
from scripts import live_emit
from scripts.live_emit import build_signed_request

MODEL = "mistral/mistral-small-latest"
HOUR = 3600.0


class _Clock:
    """Settable wall clock for expiry tests."""

    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _signed(tmp_path: Path, key: str = "k") -> tuple[bytes, dict]:
    """A real Ed25519-signed request body + headers (no network)."""
    body, headers, _ = build_signed_request(
        execute_canary(MODEL, mock=True), MODEL, tmp_path / f"{key}.id"
    )
    return body, headers


def _files(spool: Spool) -> list[Path]:
    return sorted(spool.directory.glob("*.batch.json"))


# ---------------------------------------------------------------------------
# Gateway duplicate guard (adversarial case b)
# ---------------------------------------------------------------------------


def test_duplicate_batch_id_returns_409_and_skips_cusum(tmp_path) -> None:
    """Same signed batch twice: 202 then 409; detector updated once."""
    body, headers = _signed(tmp_path)
    n_metrics = len(json.loads(body)["metrics"])
    with TestClient(app) as c:
        det = app.state.detector
        with patch.object(det, "update", wraps=det.update) as spy:
            first = c.post("/v1/signals", content=body, headers=headers)
            second = c.post("/v1/signals", content=body, headers=headers)
        rows = app.state.repo.get_recent_signals(MODEL)

    assert first.status_code == 202, first.text
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["error"] == "duplicate_batch"
    assert spy.call_count == n_metrics
    assert len(rows) == 1


def test_duplicate_guard_runs_after_signature_check(tmp_path) -> None:
    """A forged signature on a known batch_id is 401, not 409.

    Otherwise an unauthenticated caller could probe which batch_ids exist.
    """
    body, headers = _signed(tmp_path)
    forged = dict(headers, **{"x-signature": "00" * 64})
    with TestClient(app) as c:
        assert (
            c.post("/v1/signals", content=body, headers=headers).status_code
            == 202
        )
        resp = c.post("/v1/signals", content=body, headers=forged)
    assert resp.status_code == 401, resp.text


def test_sqlite_has_batch(tmp_path) -> None:
    body, headers = _signed(tmp_path)
    bid = json.loads(body)["batch_id"]
    with TestClient(app) as c:
        repo = app.state.repo
        assert repo.has_batch(bid) is False
        c.post("/v1/signals", content=body, headers=headers)
        assert repo.has_batch(bid) is True
        assert repo.has_batch("00000000-0000-0000-0000-000000000000") is False


def test_ch_has_batch_queries_by_batch_id() -> None:
    client = MagicMock()
    repo = ClickHouseRepository(client)
    client.query.return_value = MagicMock(result_rows=[[1]])
    assert repo.has_batch("abc") is True
    sql = client.query.call_args.args[0]
    assert "batch_id = {bid:String}" in sql
    assert client.query.call_args.kwargs["parameters"] == {"bid": "abc"}
    client.query.return_value = MagicMock(result_rows=[[0]])
    assert repo.has_batch("abc") is False
    client.query.return_value = MagicMock(result_rows=[])
    assert repo.has_batch("abc") is False


# ---------------------------------------------------------------------------
# Spool: storage invariants
# ---------------------------------------------------------------------------


def test_put_then_drain_delivers_exact_signed_bytes(tmp_path) -> None:
    """Round trip through disk and the real gateway (adversarial case c)."""
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    spool.put(body, headers)

    with TestClient(app) as c:

        def send(b: bytes, h: dict) -> int:
            assert b == body
            return c.post("/v1/signals", content=b, headers=h).status_code

        report = spool.drain(send)
        row = app.state.repo.get_recent_signals(MODEL)[0]

    assert report.delivered == [json.loads(body)["batch_id"]]
    assert report.remaining == 0
    assert _files(spool) == []
    signed = json.loads(body)["metrics"]
    assert row.avg_output_length == signed["avg_output_length"]
    assert row.json_success_rate == signed["json_success_rate"]


def test_put_leaves_no_temp_file(tmp_path) -> None:
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    path = spool.put(body, headers)
    names = [p.name for p in spool.directory.iterdir()]
    assert names == [path.name]
    record = json.loads(path.read_text("utf-8"))
    assert base64.b64decode(record["body_b64"]) == body


def test_put_refuses_body_with_raw_text_field(tmp_path) -> None:
    """The spool cannot carry anything the wire format does not allow."""
    body, headers = _signed(tmp_path)
    payload = json.loads(body)
    spool = Spool(tmp_path / "spool")

    leaky = dict(payload, raw_output="the model said something private")
    with pytest.raises(ValueError):
        spool.put(canonical_json(leaky), headers)

    bad_metric = dict(payload)
    bad_metric["metrics"] = dict(payload["metrics"], prompt_text=1.0)
    with pytest.raises(ValueError):
        spool.put(canonical_json(bad_metric), headers)

    bad_hash = dict(payload)
    bad_hash["canary_hashes"] = {"p": "not a hash"}
    with pytest.raises(ValueError):
        spool.put(canonical_json(bad_hash), headers)

    with pytest.raises(ValueError):  # not canonical bytes
        spool.put(json.dumps(payload, indent=2).encode(), headers)
    with pytest.raises(ValueError):  # missing signature
        spool.put(body, {"x-public-key": headers["x-public-key"]})
    assert not spool.directory.exists() or _files(spool) == []


def test_drain_order_is_oldest_first(tmp_path) -> None:
    clock = _Clock()
    spool = Spool(tmp_path / "spool", clock=clock)
    ids = []
    for i in range(3):
        body, headers = _signed(tmp_path, key=f"k{i}")
        spool.put(body, headers)
        ids.append(json.loads(body)["batch_id"])
        clock.now += 60
    seen: list[str] = []

    def send(b: bytes, h: dict) -> int:
        seen.append(json.loads(b)["batch_id"])
        return 202

    spool.drain(send)
    assert seen == ids


def test_drain_treats_409_as_delivered(tmp_path) -> None:
    """A batch that did arrive before the timeout is removed, not resent.

    Simulates the timeout-after-write case against the real gateway.
    """
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    with TestClient(app) as c:
        assert (
            c.post("/v1/signals", content=body, headers=headers).status_code
            == 202
        )
        spool.put(body, headers)  # client never saw the 202
        report = spool.drain(
            lambda b, h: (
                c.post("/v1/signals", content=b, headers=h).status_code
            )
        )
        rows = app.state.repo.get_recent_signals(MODEL)
    assert report.duplicate == [json.loads(body)["batch_id"]]
    assert _files(spool) == []
    assert len(rows) == 1


def test_drain_stops_on_5xx_and_on_transport_error(tmp_path) -> None:
    clock = _Clock()
    spool = Spool(tmp_path / "spool", clock=clock)
    for i in range(3):
        spool.put(*_signed(tmp_path, key=f"k{i}"))
        clock.now += 1
    calls: list[int] = []

    def send_503(b: bytes, h: dict) -> int:
        calls.append(1)
        return 503

    report = spool.drain(send_503)
    assert len(calls) == 1
    assert report.remaining == 3
    assert "503" in (report.stopped_on or "")
    assert len(_files(spool)) == 3

    def send_boom(b: bytes, h: dict) -> int:
        raise httpx.ConnectError("down")

    report = spool.drain(send_boom)
    assert report.remaining == 3
    assert "ConnectError" in (report.stopped_on or "")
    assert len(_files(spool)) == 3


def test_expired_entries_are_dropped(tmp_path) -> None:
    clock = _Clock()
    spool = Spool(tmp_path / "spool", clock=clock)
    spool.put(*_signed(tmp_path))
    clock.now += 30 * HOUR  # exactly at the limit: still valid
    assert len(spool.pending()) == 1
    clock.now += 1
    sent: list[bytes] = []
    report = spool.drain(lambda b, h: sent.append(b) or 202)
    assert sent == []
    assert len(report.expired) == 1
    assert _files(spool) == []


def test_cap_evicts_oldest(tmp_path) -> None:
    clock = _Clock()
    spool = Spool(tmp_path / "spool", clock=clock, max_files=2)
    ids = []
    for i in range(3):
        body, headers = _signed(tmp_path, key=f"k{i}")
        spool.put(body, headers)
        ids.append(json.loads(body)["batch_id"])
        clock.now += 1
    assert [e.batch_id for e in spool.pending()] == ids[1:]


def test_tampered_spool_file_is_quarantined_not_resent(tmp_path) -> None:
    """Adversarial case (a): bytes altered after signing.

    The altered body is still a valid, canonical SignalBatch, so the
    spool itself cannot tell; the gateway's signature check can.  The
    file must then be quarantined and never sent again.
    """
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    path = spool.put(body, headers)

    record = json.loads(path.read_text("utf-8"))
    payload = json.loads(body)
    # Fabricated drift.  Always a real change: the original value is
    # DP-noised and clamped, so it can itself be exactly 0.0 (a first
    # version of this test set 0.0 and was vacuous on such a draw).
    rate = payload["metrics"]["json_success_rate"]
    payload["metrics"]["json_success_rate"] = 1.0 if rate != 1.0 else 0.0
    tampered = canonical_json(payload)
    assert tampered != body
    record["body_b64"] = base64.b64encode(tampered).decode()
    path.write_text(json.dumps(record), "utf-8")

    calls: list[int] = []
    with TestClient(app) as c:

        def send(b: bytes, h: dict) -> int:
            status = c.post("/v1/signals", content=b, headers=h).status_code
            calls.append(status)
            return status

        report = spool.drain(send)
        again = spool.drain(send)
        rows = app.state.repo.get_recent_signals(MODEL)

    assert calls == [401]
    assert len(report.quarantined) == 1
    assert again.quarantined == [] and again.delivered == []
    assert rows == []
    assert (spool.directory / "quarantine" / path.name).exists()


def test_unreadable_spool_file_is_quarantined_unsent(tmp_path) -> None:
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    path = spool.put(body, headers)
    path.write_text("{not json", "utf-8")
    sent: list[bytes] = []
    report = spool.drain(lambda b, h: sent.append(b) or 202)
    assert sent == []
    assert report.quarantined == [path.name]


def test_drain_accounting_property(tmp_path) -> None:
    """Property: every file ends in exactly one bucket, for any outcomes.

    Seeded random sequences of statuses and failures (no hypothesis
    dependency, so CI needs nothing new).
    """
    bodies = [_signed(tmp_path, key=f"k{i}") for i in range(6)]
    rng = random.Random(20260915)
    outcomes = [202, 409, 400, 401, 422, 500, 503, "raise"]
    for trial in range(60):
        clock = _Clock()
        spool = Spool(tmp_path / f"s{trial}", clock=clock)
        n = rng.randint(0, len(bodies))
        for body, headers in bodies[:n]:
            spool.put(body, headers)
            clock.now += rng.choice([1, HOUR, 10 * HOUR])
        clock.now += rng.choice([0, 20 * HOUR, 31 * HOUR])
        plan = [rng.choice(outcomes) for _ in range(n)]

        def send(b: bytes, h: dict, _plan=plan) -> int:
            step = _plan.pop(0)
            if step == "raise":
                raise OSError("network")
            return step

        report = spool.drain(send)
        acted = (
            len(report.delivered)
            + len(report.duplicate)
            + len(report.quarantined)
            + len(report.expired)
        )
        assert acted + report.remaining == n, (trial, report)
        assert len(_files(spool)) == report.remaining, (trial, report)


# ---------------------------------------------------------------------------
# live_emit wiring
# ---------------------------------------------------------------------------


def test_post_status_returns_http_error_code(monkeypatch) -> None:
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 409, "Conflict", {}, io.BytesIO(b'{"x": 1}')
        )

    monkeypatch.setattr(live_emit.urllib.request, "urlopen", fake_urlopen)
    status, resp = live_emit._post_status("http://gw/v1/signals", b"{}", {}, 1)
    assert status == 409
    assert resp == {"x": 1}

    def down(req, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(live_emit.urllib.request, "urlopen", down)
    with pytest.raises(live_emit.GatewayTransportError):
        live_emit._post_status("http://gw/v1/signals", b"{}", {}, 1)


@pytest.mark.parametrize(
    ("result", "outcome", "spooled"),
    [
        (live_emit.GatewayTransportError("down"), "spooled", True),
        ((503, None), "spooled", True),
        ((202, {"batch_id": "b"}), "accepted", False),
        ((409, {}), "duplicate", False),
        ((422, {}), "rejected", False),
        ((401, {}), "rejected", False),
    ],
)
def test_deliver_spools_on_transport_error(
    tmp_path, monkeypatch, result, outcome, spooled
) -> None:
    def fake(endpoint, body, headers, timeout):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(live_emit, "_post_status", fake)
    body, headers = _signed(tmp_path)
    spool = Spool(tmp_path / "spool")
    got, _ = live_emit.deliver("http://gw", body, headers, spool)
    assert got == outcome
    assert (len(_files(spool)) == 1) is spooled


def test_deliver_without_spool_reports_lost(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(live_emit, "_post_status", lambda *a, **k: (502, None))
    body, headers = _signed(tmp_path)
    got, _ = live_emit.deliver("http://gw", body, headers, None)
    assert got == "lost"


def test_open_spool_respects_off(tmp_path) -> None:
    assert live_emit.open_spool("off") is None
    assert live_emit.open_spool("OFF") is None
    assert live_emit.open_spool(str(tmp_path)).directory == tmp_path
    assert live_emit.open_spool(None).directory == Path(".seismograph_spool")


def test_main_drains_spool_before_probing(tmp_path, monkeypatch) -> None:
    """The backlog goes out even when this run's provider fails."""
    body, headers = _signed(tmp_path)
    spool_dir = tmp_path / "spool"
    Spool(spool_dir).put(body, headers)

    order: list[str] = []

    def fake_post(endpoint, b, h, timeout):
        order.append("post")
        return 202, {}

    def fake_run(*a, **k):
        order.append("probe")
        raise ProviderError("provider down")

    monkeypatch.setattr(live_emit, "_post_status", fake_post)
    monkeypatch.setattr(live_emit, "execute_canary_strict", fake_run)
    monkeypatch.setenv("SEISMOGRAPH_SPOOL_DIR", str(spool_dir))
    monkeypatch.setenv("SEISMOGRAPH_PROBE_KEY_PATH", str(tmp_path / "k.id"))

    assert live_emit.main() == 1
    assert order == ["post", "probe"]
    assert _files(Spool(spool_dir)) == []


def test_main_spools_and_exits_1_when_gateway_down(
    tmp_path, monkeypatch
) -> None:
    spool_dir = tmp_path / "spool"

    def down(endpoint, b, h, timeout):
        raise live_emit.GatewayTransportError("down")

    monkeypatch.setattr(live_emit, "_post_status", down)
    monkeypatch.setattr(
        live_emit,
        "execute_canary_strict",
        lambda *a, **k: execute_canary(MODEL, mock=True),
    )
    monkeypatch.setenv("SEISMOGRAPH_SPOOL_DIR", str(spool_dir))
    monkeypatch.setenv("SEISMOGRAPH_PROBE_KEY_PATH", str(tmp_path / "k.id"))
    monkeypatch.setenv("SEISMOGRAPH_PROBE_MODEL_TUPLE", MODEL)

    assert live_emit.main() == 1
    assert len(_files(Spool(spool_dir))) == 1


# ---------------------------------------------------------------------------
# SDK wiring
# ---------------------------------------------------------------------------


def _sdk(tmp_path: Path, client: MagicMock, spool: bool = True) -> ProbeSDK:
    config = ProbeConfig(
        model_tuple=MODEL,
        suite_version_hash="a" * 64,
        gateway_endpoint="http://gw/v1/signals",
        spool_dir=str(tmp_path / "spool") if spool else None,
    )
    return ProbeSDK(
        config,
        _http_client=client,
        _key_manager=KeyManager(key_path=tmp_path / "sdk.id"),
    )


def _stage(sdk: ProbeSDK) -> None:
    span = sdk.start_canary_span(prompt_count=1)
    span.attributes["gen_ai.usage.output_tokens"] = 100
    span.attributes["gen_ai.response.json_valid"] = True
    sdk.finish_canary_span(status_code="OK")


def _client(*statuses) -> MagicMock:
    client = MagicMock()
    responses = []
    for s in statuses:
        if isinstance(s, Exception):
            responses.append(s)
        else:
            r = MagicMock(status_code=s, text="")
            r.json.return_value = {"status": "accepted"}
            responses.append(r)
    client.post.side_effect = responses
    return client


def test_flush_spools_on_503_and_continues(tmp_path) -> None:
    client = _client(503)
    sdk = _sdk(tmp_path, client)
    _stage(sdk)
    out = sdk.flush()
    assert out["status"] == "spooled"
    assert out["batches"][0]["status"] == "spooled"
    stored = Spool(tmp_path / "spool").pending()
    assert len(stored) == 1
    sent = client.post.call_args.kwargs["content"]
    assert stored[0].body == sent


def test_flush_spools_on_transport_error(tmp_path) -> None:
    client = _client(httpx.ConnectTimeout("slow"))
    sdk = _sdk(tmp_path, client)
    _stage(sdk)
    out = sdk.flush()
    assert out["status"] == "spooled"
    assert len(Spool(tmp_path / "spool").pending()) == 1


def test_flush_without_spool_keeps_old_contract(tmp_path) -> None:
    sdk = _sdk(tmp_path, _client(httpx.ConnectTimeout("slow")), spool=False)
    _stage(sdk)
    with pytest.raises(httpx.ConnectTimeout):
        sdk.flush()
    sdk = _sdk(tmp_path, _client(503), spool=False)
    _stage(sdk)
    with pytest.raises(RuntimeError, match="503"):
        sdk.flush()


def test_flush_4xx_still_raises_with_spool(tmp_path) -> None:
    sdk = _sdk(tmp_path, _client(422))
    _stage(sdk)
    with pytest.raises(RuntimeError, match="422"):
        sdk.flush()
    assert Spool(tmp_path / "spool").pending() == []


def test_flush_drains_spool_before_new_batches(tmp_path) -> None:
    old_body, old_headers = _signed(tmp_path)
    Spool(tmp_path / "spool").put(old_body, old_headers)
    client = _client(202, 202)
    sdk = _sdk(tmp_path, client)
    _stage(sdk)
    out = sdk.flush()
    first = client.post.call_args_list[0].kwargs["content"]
    second = client.post.call_args_list[1].kwargs["content"]
    assert first == old_body
    assert second != old_body
    assert out["status"] == "ok"
    assert "delivered=1" in out["spool"]
    assert Spool(tmp_path / "spool").pending() == []


def test_flush_409_is_duplicate_not_error(tmp_path) -> None:
    sdk = _sdk(tmp_path, _client(409), spool=False)
    _stage(sdk)
    out = sdk.flush()
    assert out["batches"][0]["status"] == "duplicate"


def test_dry_run_never_drains(tmp_path) -> None:
    Spool(tmp_path / "spool").put(*_signed(tmp_path))
    client = _client()
    config = ProbeConfig(
        model_tuple=MODEL,
        suite_version_hash="a" * 64,
        gateway_endpoint="http://gw/v1/signals",
        spool_dir=str(tmp_path / "spool"),
        dry_run=True,
    )
    sdk = ProbeSDK(
        config,
        _http_client=client,
        _key_manager=KeyManager(key_path=tmp_path / "sdk.id"),
    )
    _stage(sdk)
    sdk.flush()
    client.post.assert_not_called()
    assert len(Spool(tmp_path / "spool").pending()) == 1
