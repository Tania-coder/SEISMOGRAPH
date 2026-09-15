"""
scripts/live_emit.py
====================
End-to-end LIVE emission: run the canary suite against a real
OpenAI-compatible endpoint, aggregate the results into a DP-noised,
Ed25519-signed SignalBatch, and POST it to a running gateway's
``/v1/signals`` endpoint so the public "model weather" dashboard shows a
REAL model tuple instead of demo data.

This is Track 1b: the first time a live probe result travels the full
privacy + signing + ingestion path end to end.

Pipeline:
  execute_canary_strict(suite=CANARY_SUITE_V2, mock=False, provider)
    -> [CanaryResult]  (all 50 or nothing -- see PartialSuiteError)
    -> Aggregator.add_result / .flush  (clamp + Laplace DP noise, eps=2.0)
    -> SignalBatch (frozen, fleet_id=None => public network path)
    -> canonical_json(payload)          (the exact signed bytes)
    -> Ed25519 sign  (probe identity key, .seismograph_id, gitignored)
    -> POST {gateway}/v1/signals  with x-signature + x-public-key headers
    -> (optional) GET {gateway}/v1/weather to show the model row

Privacy: only the DP-noised aggregate metrics, SHA-256 hashes, and counts
are transmitted. Raw prompt text and raw model output never leave the probe
perimeter and are never printed.

Configuration (environment variables):
  SEISMOGRAPH_PROBE_BASE_URL     default http://localhost:11434/v1
  SEISMOGRAPH_PROBE_API_KEY      bearer token (omit for local Ollama)
  SEISMOGRAPH_PROBE_MODEL_TUPLE  default ollama/llama3.1
  SEISMOGRAPH_PROBE_MAX_TOKENS   default 64
  SEISMOGRAPH_PROBE_DELAY_MS     default 0    (inter-prompt pacing, CAN-2a)
  SEISMOGRAPH_PROBE_MAX_RETRIES  default 2    (transient 429/503 only)
  SEISMOGRAPH_GATEWAY_ENDPOINT   default http://localhost:8000/v1/signals
  SEISMOGRAPH_PROBE_KEY_PATH     default .seismograph_id
  SEISMOGRAPH_SPOOL_DIR          default .seismograph_spool
                                 ("off" disables the spool, BUF-1)

Spool (BUF-1): a signed batch whose POST fails with a transport error or
a 5xx is written to SEISMOGRAPH_SPOOL_DIR and re-sent first on the next
run (before the new suite is probed).  The run still exits 1, so a
failed delivery stays visible.  A 409 from the gateway means it already
holds that batch_id and counts as delivered.  NOTE: on an ephemeral CI
runner the spool directory does not survive the job.

Pacing (CAN-2a): a rate-limited free tier cannot serve 50 sequential
calls -- google/gemini-3.5-flash-lite completed 18 of 50 on 2026-07-31
and the whole run was (correctly) discarded.  Set
SEISMOGRAPH_PROBE_DELAY_MS per matrix leg to spread the suite under the
provider's requests-per-minute quota.  The default of 0 leaves every
other leg exactly as it was.

Example (Mistral -> local gateway):
  # terminal 1:  uvicorn gateway.main:app --port 8000
  # terminal 2:
  SEISMOGRAPH_PROBE_BASE_URL=https://api.mistral.ai/v1 \
  SEISMOGRAPH_PROBE_API_KEY=... \
  SEISMOGRAPH_PROBE_MODEL_TUPLE=mistral/mistral-small-latest \
  python scripts/live_emit.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Make the repository root importable when run directly as a script.
# #SG-TRACE: REQ-CANARY-024
# #   | assumption: repo root is the parent directory of scripts/
# #   | test: tests/test_live_emit.py imports the build helper offline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe.canary import (  # noqa: E402
    CANARY_SUITE_V2,
    DEFAULT_MAX_RETRIES,
    SUITE_VERSION_V2,
    PartialSuiteError,
    execute_canary_strict,
    pacing_budget_ms,
)
from probe.crypto import (  # noqa: E402
    KeyManager,
    canonical_json,
    sign_payload,
)
from probe.privacy import Aggregator  # noqa: E402
from probe.providers import (  # noqa: E402
    OpenAICompatibleProvider,
    ProviderError,
)
from probe.spool import DEFAULT_SPOOL_DIR, Spool  # noqa: E402


class GatewayTransportError(RuntimeError):
    """The gateway could not be reached (no HTTP status at all)."""


def build_signed_request(
    results: list,
    model_tuple: str,
    key_path: str | Path,
) -> tuple[bytes, dict, dict]:
    """Aggregate canary results into a signed, ready-to-POST request.

    Pure and network-free so it is unit-testable offline: takes already
    executed CanaryResults, returns the exact request body bytes, the HTTP
    headers (signature + public key), and the plain payload dict (for
    display/inspection only).

    The body bytes are the canonical JSON that the signature is computed
    over -- the gateway verifies the signature against the raw body, so the
    two MUST be byte-identical.

    #SG-TRACE: REQ-AUTH-002
    #   | assumption: gateway verifies Ed25519 sig over the raw request body
    #     which equals canonical_json(payload)
    #   | test: test_live_emit_round_trip_accepts_and_shows_model
    #SG-TRACE: REQ-PRIV-020
    #   | assumption: only DP-noised aggregates + hashes leave the probe;
    #     no raw output is present on the SignalBatch
    #   | test: test_live_emit_payload_has_no_raw_output
    """
    aggregator = Aggregator()
    for result in results:
        aggregator.add_result(result)
    # fleet_id=None => public network path (subject to quorum gating).
    batch = aggregator.flush(model_tuple, fleet_id=None)

    payload = batch.to_dict()
    body = canonical_json(payload)

    key_manager = KeyManager(Path(key_path))
    signature_hex = sign_payload(payload, key_manager.private_key)
    headers = {
        "Content-Type": "application/json",
        "x-signature": signature_hex,
        "x-public-key": key_manager.public_key_hex,
    }
    return body, headers, payload


def _post_status(
    endpoint: str, body: bytes, headers: dict, timeout: float
) -> tuple[int, dict | None]:
    """POST *body*; return (HTTP status, decoded JSON or None).

    Any HTTP status, success or error, is returned.  Only a failure to
    get a status at all raises GatewayTransportError.

    #SG-TRACE: REQ-BUF-006
    #   | assumption: urllib raises HTTPError for every non-2xx status,
    #     and URLError / OSError / TimeoutError when no status exists
    #   | test: test_post_status_returns_http_error_code
    """
    req = urllib.request.Request(
        endpoint, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        try:
            return exc.code, json.loads(detail)
        except json.JSONDecodeError:
            return exc.code, {"detail": detail}
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise GatewayTransportError(f"gateway unreachable: {reason}") from None
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, None


def open_spool(value: str | None) -> Spool | None:
    """Return the configured Spool, or None when disabled with "off"."""
    if value is None or value == "":
        value = DEFAULT_SPOOL_DIR
    if value.strip().lower() == "off":
        return None
    return Spool(value)


def deliver(
    endpoint: str,
    body: bytes,
    headers: dict,
    spool: Spool | None,
    timeout: float = 30.0,
) -> tuple[str, dict | None]:
    """Send one new signed batch; spool it if the failure is transient.

    Returns (outcome, response) where outcome is one of
    "accepted", "duplicate", "rejected", "spooled", "lost".

    #SG-TRACE: REQ-BUF-007
    #   | assumption: only a missing status or a 5xx is worth retrying;
    #     a 4xx (other than 409) will fail identically next time
    #   | test: test_deliver_spools_on_transport_error
    """
    try:
        status, resp = _post_status(endpoint, body, headers, timeout)
    except GatewayTransportError as exc:
        status, resp = None, {"detail": str(exc)}
    if status == 202:
        return "accepted", resp
    if status == 409:
        return "duplicate", resp
    if status is not None and 400 <= status < 500:
        return "rejected", {"status": status, **(resp or {})}
    if spool is None:
        return "lost", {"status": status, **(resp or {})}
    path = spool.put(body, headers)
    return "spooled", {"status": status, "path": str(path), **(resp or {})}


def _weather_for(base: str, model_tuple: str, timeout: float) -> dict | None:
    """GET {base}/v1/weather and return the row for *model_tuple*, if any."""
    url = base.rstrip("/") + "/v1/weather"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError):
        return None
    for row in rows:
        if row.get("model_tuple") == model_tuple:
            return row
    return None


def main() -> int:
    base_url = os.environ.get(
        "SEISMOGRAPH_PROBE_BASE_URL", "http://localhost:11434/v1"
    )
    api_key = os.environ.get("SEISMOGRAPH_PROBE_API_KEY") or None
    model_tuple = os.environ.get(
        "SEISMOGRAPH_PROBE_MODEL_TUPLE", "ollama/llama3.1"
    )
    max_tokens = int(os.environ.get("SEISMOGRAPH_PROBE_MAX_TOKENS", "64"))
    # CAN-2a: per-leg pacing.  Both default to the pre-CAN-2a behaviour
    # of the runner (no pacing; the runner's own retry default), so a
    # leg that sets neither variable is unchanged.
    # SG-TRACE: REQ-CAN2A-011
    #   | assumption: pacing is a per-leg operational setting, not a
    #     property of the corpus, so it arrives from the environment
    #     (the workflow matrix) and never from a constant in the probe
    #   | test: test_live_emit_reads_pacing_env_and_passes_it_through
    delay_ms = int(os.environ.get("SEISMOGRAPH_PROBE_DELAY_MS", "0"))
    max_retries = int(
        os.environ.get(
            "SEISMOGRAPH_PROBE_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)
        )
    )
    gateway = os.environ.get(
        "SEISMOGRAPH_GATEWAY_ENDPOINT", "http://localhost:8000/v1/signals"
    )
    key_path = os.environ.get("SEISMOGRAPH_PROBE_KEY_PATH", ".seismograph_id")
    gateway_base = gateway.split("/v1/signals")[0]
    spool = open_spool(os.environ.get("SEISMOGRAPH_SPOOL_DIR"))

    # BUF-1: re-send anything a previous run could not deliver, BEFORE
    # probing, so an older batch reaches the gateway before a newer one
    # and a provider failure in this run does not block the backlog.
    # #SG-TRACE: REQ-BUF-008
    # #   | assumption: the drain runs whatever happens to the provider
    # #   | test: test_main_drains_spool_before_probing
    if spool is not None:

        def _send(body: bytes, headers: dict) -> int:
            status, _ = _post_status(gateway, body, headers, timeout=30.0)
            return status

        report = spool.drain(_send)
        print(report.summary())

    print(f"Probing {model_tuple} via {base_url} ...")
    if delay_ms > 0:
        budget_s = pacing_budget_ms(len(CANARY_SUITE_V2), delay_ms) / 1000.0
        print(
            f"  pacing: {delay_ms} ms between prompts, "
            f"<= {max_retries} retries on 429/503, "
            f"worst-case added wall-clock {budget_s:.0f}s"
        )
    try:
        provider = OpenAICompatibleProvider(
            base_url=base_url, api_key=api_key, max_tokens=max_tokens
        )
        # CAN-2 cutover: suite v2.0.0 (50 prompts), all-or-nothing.
        # A partial run would flush at a reduced n, which silently changes
        # the DP sensitivity (delta_f = MAX/n) and therefore the meaning of
        # every metric in the batch -- so a partial run is discarded.
        # #SG-TRACE: REQ-CAN2-CUTOVER-001
        # #   | assumption: discarding a partial leg is strictly safer than
        # #     emitting a batch whose n differs from the suite size
        # #   | test: test_partial_suite_run_is_discarded_not_flushed
        results = execute_canary_strict(
            model_tuple,
            suite=CANARY_SUITE_V2,
            suite_version=SUITE_VERSION_V2,
            mock=False,
            provider=provider,
            delay_ms=delay_ms,
            max_retries=max_retries,
        )
    except PartialSuiteError as exc:
        print(
            f"Partial suite run discarded: {exc}",
            file=sys.stderr,
        )
        return 1
    except ProviderError as exc:
        print(f"Provider call failed: {exc}", file=sys.stderr)
        return 1

    body, headers, payload = build_signed_request(
        results, model_tuple, key_path
    )
    print(
        f"Built signed SignalBatch: {len(body)} bytes, "
        f"key {headers['x-public-key'][:12]}..."
    )
    print(
        "  DP-noised metrics: "
        f"avg_output_length={payload['metrics']['avg_output_length']:.1f}, "
        f"json_success_rate={payload['metrics']['json_success_rate']:.3f}, "
        f"result_count={payload['result_count']}"
    )

    print(f"POST {gateway} ...")
    outcome, resp = deliver(gateway, body, headers, spool, timeout=30.0)
    resp = resp or {}
    if outcome == "spooled":
        print(
            f"Emission failed ({resp.get('status') or 'no status'}); "
            f"signed batch kept for the next run: {resp.get('path')}",
            file=sys.stderr,
        )
        return 1
    if outcome in ("rejected", "lost"):
        print(f"Emission failed: {outcome} {resp}", file=sys.stderr)
        return 1
    print(f"  -> {outcome} batch_id={resp.get('batch_id')}")

    row = _weather_for(gateway_base, model_tuple, timeout=10.0)
    if row is not None:
        print(
            f"\nDashboard now shows REAL model {model_tuple}: "
            f"status={row.get('status')}, "
            f"avg_len={row.get('recent_avg_output_length')}, "
            f"json_rate={row.get('recent_json_success_rate')}"
        )
        print(f"Open the dashboard: {gateway_base}/dashboard")
    print(
        "\nPrivacy: only DP-noised aggregates, SHA-256 hashes and counts "
        "were transmitted -- no raw output."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
