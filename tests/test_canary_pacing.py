"""
tests.test_canary_pacing
========================
CAN-2a: provider pacing + transient-error backoff for the strict runner.

All tests run fully OFFLINE and NONE of them sleeps.  Every call into
``execute_canary_strict`` passes an injected ``sleeper`` (a ``_FakeClock``
that records the requested durations instead of waiting), and an autouse
fixture replaces ``time.sleep`` with a raising stub so an accidental
direct call inside the runner fails the test instead of slowing CI
(contract C7/R3).

Covers the CAN-2a Stage-1 contract test table (section 6):
  P1  delay_ms=0 -> identical results to today; clock records no sleeps
  P2  delay_ms=250 over 50 prompts -> exactly 49 sleeps of 250 ms
  P3  429 twice then success -> prompt succeeds, waits strictly increase
  P4  429 forever -> PartialSuiteError, retries bounded (per prompt AND
      run-wide by the total backoff ceiling)
  P5  400 -> no retry, prompt fails immediately
  P6  1 transient-failing prompt + 49 clean -> 50 results, no exception
  P7  transport ProviderError -> status_code is None, not retried
  P8  pacing budget at the google setting fits the Actions job timeout

  ADV-1 an always-429 provider emits ZERO batches (no retry-driven
        amplification) and one org still cannot promote a public alert
  ADV-2 a paced run and an unpaced run over the SAME fixture responses
        produce byte-identical metrics: pacing moves timing, not features

#SG-TRACE: REQ-CAN2A-001..011 | tests below
"""

from __future__ import annotations

import random
import time
import urllib.error
from collections.abc import Callable
from inspect import signature

import pytest
import scripts.live_emit as live_emit
from engine.correlation import (
    AgreementScorer,
    ChangePointResult,
    required_quorum,
)
from probe.canary import (
    CANARY_SUITE_V2,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOTAL_BACKOFF_MS,
    RETRY_BACKOFF_BASE_MS,
    SUITE_VERSION_V2,
    TRANSIENT_STATUS_CODES,
    CanaryResult,
    PartialSuiteError,
    _mock_text_for,
    _mock_tool_calls_for,
    execute_canary,
    execute_canary_strict,
    pacing_budget_ms,
)
from probe.privacy import Aggregator
from probe.providers import (
    CompletionResult,
    ProviderError,
    _urllib_transport,
)

MODEL = "openai/gpt-4o@2025-08"

# Captured before the no-real-sleep fixture can touch it, so the default
# argument of execute_canary_strict can be identified.
_REAL_SLEEP: Callable[[float], None] = time.sleep


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real sleep in this module an immediate test failure.

    The runner's default sleeper is bound at definition time, so this
    patch does not (and must not) change that default -- what it does
    catch is a direct ``time.sleep(...)`` call inside the runner body,
    which is exactly the regression C7 exists to prevent.
    """

    def _boom(seconds: float) -> None:  # pragma: no cover - guard only
        raise AssertionError(
            f"a test tried to really sleep for {seconds}s; "
            "inject a fake clock instead (contract CAN-2a C7)"
        )

    monkeypatch.setattr(time, "sleep", _boom)


class _FakeClock:
    """Injected sleeper: records requested durations, never waits.

    ``seconds`` is the raw argument list (the runner speaks seconds, as
    ``time.sleep`` does); ``ms`` is the same list in milliseconds for
    readable assertions.
    """

    def __init__(self) -> None:
        self.seconds: list[float] = []
        self.events: list[tuple[str, object]] = []

    def __call__(self, seconds: float) -> None:
        self.seconds.append(seconds)
        self.events.append(("sleep", seconds))

    @property
    def ms(self) -> list[float]:
        return [round(s * 1000, 6) for s in self.seconds]

    @property
    def total_s(self) -> float:
        return sum(self.seconds)


def _http(status: int) -> ProviderError:
    """A ProviderError as the transport raises it for an HTTP status."""
    return ProviderError(f"provider HTTP {status}", status_code=status)


def _transport_failure() -> ProviderError:
    """A ProviderError with no HTTP status at all (socket/DNS/timeout)."""
    return ProviderError("provider unreachable: TimeoutError")


class _ScriptedProvider:
    """complete_ex driven by a per-prompt script of exceptions.

    ``script`` maps a user prompt to the exceptions to raise on its
    first calls (one entry consumed per call; an exhausted or absent
    entry answers normally).  ``always`` raises a fresh exception from
    the given factory on every call, forever.

    Answers are the frozen mocks of the corpus, so a completed run
    produces exactly the features an offline mock run produces.
    """

    def __init__(
        self,
        script: dict[str, list[BaseException]] | None = None,
        always: Callable[[], BaseException] | None = None,
        clock: _FakeClock | None = None,
    ) -> None:
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.always = always
        self.clock = clock
        self.calls: list[str] = []
        self._by_user = {p["user"]: p for p in CANARY_SUITE_V2}

    def complete_ex(
        self,
        model: str,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        self.calls.append(user)
        if self.clock is not None:
            self.clock.events.append(("call", user))
        if self.always is not None:
            raise self.always()
        pending = self.script.get(user)
        if pending:
            raise pending.pop(0)
        prompt = self._by_user.get(user)
        pid = prompt["prompt_id"] if prompt else "v1.0.0-logic"
        if tools:
            return CompletionResult(
                text="",
                tool_calls_json=_mock_tool_calls_for(pid),
                output_tokens=12,
                reasoning_tokens=4,
                latency_ms=41,
            )
        return CompletionResult(
            text=_mock_text_for(pid),
            tool_calls_json=None,
            output_tokens=12,
            reasoning_tokens=4,
            latency_ms=41,
        )


def _features(results: list[CanaryResult]) -> list[tuple]:
    """Everything about a result except its wall-clock timestamp."""
    return [
        (
            r.model_tuple,
            r.suite_version,
            r.prompt_id,
            r.response_hash,
            r.output_length,
            r.json_valid,
            r.latency_ms,
            r.tool_call_valid,
            r.output_tokens,
            r.reasoning_tokens,
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# P1 -- delay_ms=0 is the pre-CAN-2a code path
# ---------------------------------------------------------------------------


def test_p1_delay_zero_is_bit_for_bit_current_behaviour() -> None:
    """P1/A1: delay_ms=0 changes nothing and never calls the sleeper.

    Three runs are compared: the pre-CAN-2a call shape (no new keyword
    at all), the explicit delay_ms=0 call, and plain execute_canary.
    All three must agree on every derived feature -- and the injected
    clock must record NOTHING, because at delay 0 the runner does not
    call the sleeper at all (not "calls it with 0").

    #SG-TRACE: REQ-CAN2A-008 | test: (this)
    """
    clock = _FakeClock()
    legacy = execute_canary_strict(
        MODEL, suite=CANARY_SUITE_V2, mock=True, suite_version=SUITE_VERSION_V2
    )
    paced_zero = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=True,
        suite_version=SUITE_VERSION_V2,
        delay_ms=0,
        sleeper=clock,
    )
    plain = execute_canary(
        MODEL, suite=CANARY_SUITE_V2, mock=True, suite_version=SUITE_VERSION_V2
    )

    assert clock.seconds == []
    assert len(paced_zero) == 50
    assert _features(paced_zero) == _features(legacy) == _features(plain)


def test_default_sleeper_is_time_sleep_and_defaults_are_backward_safe() -> (
    None
):
    """A1/C1: every CAN-2a keyword defaults to the old behaviour.

    #SG-TRACE: REQ-CAN2A-008 | test: (this)
    """
    params = signature(execute_canary_strict).parameters
    assert params["delay_ms"].default == 0
    assert params["max_retries"].default == DEFAULT_MAX_RETRIES == 2
    assert params["sleeper"].default is _REAL_SLEEP
    # The pre-CAN-2a parameters keep their order, so positional call
    # sites (model_tuple, suite, mock, provider, suite_version) still
    # bind to the same names.
    assert list(params)[:5] == [
        "model_tuple",
        "suite",
        "mock",
        "provider",
        "suite_version",
    ]


# ---------------------------------------------------------------------------
# P2 -- pacing arithmetic
# ---------------------------------------------------------------------------


def test_p2_fifty_prompts_sleep_exactly_forty_nine_times() -> None:
    """P2/A2: 49 sleeps of 250 ms -- not 50, not 51.

    Order is asserted too, not just the count: the event log must start
    with a provider call and end with a provider call, so no sleep
    happens before the first prompt or after the last one.

    #SG-TRACE: REQ-CAN2A-009 | test: (this)
    """
    clock = _FakeClock()
    provider = _ScriptedProvider(clock=clock)
    results = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=False,
        provider=provider,
        suite_version=SUITE_VERSION_V2,
        delay_ms=250,
        sleeper=clock,
    )

    assert len(results) == 50
    assert len(clock.seconds) == 49
    assert clock.ms == [250.0] * 49
    assert clock.total_s == pytest.approx(12.25)
    # Strict alternation call, sleep, call, ... , call.
    kinds = [kind for kind, _ in clock.events]
    assert kinds[0] == "call"
    assert kinds[-1] == "call"
    assert kinds == ["call", "sleep"] * 49 + ["call"]


def test_p2_single_prompt_suite_never_sleeps() -> None:
    """Boundary of the n-1 rule: a 1-prompt suite sleeps 0 times.

    #SG-TRACE: REQ-CAN2A-009 | test: (this)
    """
    clock = _FakeClock()
    results = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2[:1],
        mock=True,
        suite_version=SUITE_VERSION_V2,
        delay_ms=9_000,
        sleeper=clock,
    )
    assert len(results) == 1
    assert clock.seconds == []


# ---------------------------------------------------------------------------
# P3/P4/P5/P7 -- retry classification and bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", sorted(TRANSIENT_STATUS_CODES))
def test_p3_transient_then_success_waits_strictly_increase(
    status: int,
) -> None:
    """P3/A3: 429 (and 503) twice, then success -- 2 increasing waits.

    #SG-TRACE: REQ-CAN2A-005 | test: (this)
    """
    prompt = CANARY_SUITE_V2[0]
    clock = _FakeClock()
    provider = _ScriptedProvider(
        script={prompt["user"]: [_http(status), _http(status)]},
        clock=clock,
    )
    results = execute_canary_strict(
        MODEL,
        suite=[prompt],
        mock=False,
        provider=provider,
        suite_version=SUITE_VERSION_V2,
        sleeper=clock,
    )

    assert len(results) == 1
    assert results[0].prompt_id == prompt["prompt_id"]
    assert len(provider.calls) == 3  # 1 attempt + 2 retries
    assert clock.ms == [
        float(RETRY_BACKOFF_BASE_MS),
        float(2 * RETRY_BACKOFF_BASE_MS),
    ]
    assert clock.ms[1] > clock.ms[0]  # exponential, not constant (R2)
    # No pacing was configured, so every recorded sleep is a backoff.
    assert len(clock.seconds) == 2


def test_p4_transient_forever_is_bounded_by_max_retries() -> None:
    """P4/A6: 429 forever -> PartialSuiteError with accurate counts.

    #SG-TRACE: REQ-CAN2A-005 | test: (this)
    """
    suite = CANARY_SUITE_V2[:3]
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(429), clock=clock)

    with pytest.raises(PartialSuiteError) as exc_info:
        execute_canary_strict(
            MODEL,
            suite=suite,
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            max_retries=2,
            sleeper=clock,
        )

    exc = exc_info.value
    assert exc.completed == 0
    assert exc.expected == 3
    assert exc.failed_prompt_ids == [p["prompt_id"] for p in suite]
    # 3 attempts per prompt (1 + max_retries), never a fourth.
    assert len(provider.calls) == 9
    assert clock.ms == [5000.0, 10000.0] * 3


def test_p4_transient_forever_is_bounded_by_total_budget() -> None:
    """P4/C4: the run-wide ceiling stops a 50-prompt retry storm.

    Per-prompt bounding alone is not enough: 50 prompts x (5s + 10s)
    would be 12.5 minutes of sleeping inside a 15-minute Actions job.
    Once the run-wide backoff budget is spent, the remaining prompts
    fail immediately -- fast failure, not a slow one.

    #SG-TRACE: REQ-CAN2A-004 | test: (this)
    """
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(503), clock=clock)

    with pytest.raises(PartialSuiteError) as exc_info:
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2,
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            delay_ms=250,
            sleeper=clock,
        )

    assert exc_info.value.completed == 0
    assert exc_info.value.expected == 50
    backoff_ms = sum(clock.ms) - 49 * 250.0
    assert backoff_ms == float(DEFAULT_MAX_TOTAL_BACKOFF_MS)
    assert backoff_ms <= DEFAULT_MAX_TOTAL_BACKOFF_MS
    # Every prompt was still attempted once (the leg is not abandoned),
    # but only the first few could afford retries.
    assert len(provider.calls) < 50 * (1 + DEFAULT_MAX_RETRIES)
    assert len(provider.calls) >= 50
    # Total added wall-clock stays inside the advertised budget.
    assert clock.total_s * 1000 <= pacing_budget_ms(50, 250)


def test_p5_non_transient_status_is_not_retried() -> None:
    """P5/A4: a 400 fails the prompt immediately, with no wait.

    #SG-TRACE: REQ-CAN2A-003 | test: (this)
    """
    prompt = CANARY_SUITE_V2[0]
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(400), clock=clock)

    with pytest.raises(PartialSuiteError) as exc_info:
        execute_canary_strict(
            MODEL,
            suite=[prompt],
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            sleeper=clock,
        )

    assert exc_info.value.failed_prompt_ids == [prompt["prompt_id"]]
    assert len(provider.calls) == 1
    assert clock.seconds == []


@pytest.mark.parametrize("status", [400, 401, 403, 404, 418, 500, 502])
def test_p5_only_429_and_503_are_transient(status: int) -> None:
    """A4: the transient set is exactly {429, 503}, nothing else.

    500 and 502 are deliberately excluded: a persistent 5xx that is not
    503 has, in this project's evidence, meant a bad request shape
    rather than a temporary outage, and re-issuing it spends quota to
    obtain the identical failure.

    #SG-TRACE: REQ-CAN2A-003 | test: (this)
    """
    assert status not in TRANSIENT_STATUS_CODES
    assert TRANSIENT_STATUS_CODES == frozenset({429, 503})
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(status), clock=clock)
    with pytest.raises(PartialSuiteError):
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2[:1],
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            sleeper=clock,
        )
    assert len(provider.calls) == 1
    assert clock.seconds == []


def test_p7_transport_failure_has_no_status_and_is_not_retried() -> None:
    """P7/A7: a status-less ProviderError is never retried.

    A socket timeout has no HTTP status, so it cannot be classified as
    transient without guessing -- and guessing would mean parsing the
    message string, which contract C3 forbids.

    #SG-TRACE: REQ-CAN2A-003 | test: (this)
    """
    err = _transport_failure()
    assert err.status_code is None

    clock = _FakeClock()
    provider = _ScriptedProvider(always=_transport_failure, clock=clock)
    with pytest.raises(PartialSuiteError):
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2[:1],
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            sleeper=clock,
        )
    assert len(provider.calls) == 1
    assert clock.seconds == []


def test_p7_legacy_provider_error_without_status_is_not_retried() -> None:
    """A7 backward compat: pre-CAN-2a construction sites still work.

    ``ProviderError("provider HTTP 503")`` -- the exact shape existing
    tests use -- carries NO structured status, so it is not retried and
    those tests keep their call counts.  This is the string-parsing ban
    made observable.

    #SG-TRACE: REQ-CAN2A-001 | test: (this)
    """
    legacy = ProviderError("provider HTTP 503")
    assert legacy.status_code is None
    assert str(legacy) == "provider HTTP 503"

    clock = _FakeClock()
    provider = _ScriptedProvider(
        always=lambda: ProviderError("provider HTTP 503"), clock=clock
    )
    with pytest.raises(PartialSuiteError):
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2[:2],
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            sleeper=clock,
        )
    assert len(provider.calls) == 2
    assert clock.seconds == []


def test_retries_can_be_disabled_entirely() -> None:
    """max_retries=0 reproduces the pre-CAN-2a failure behaviour.

    #SG-TRACE: REQ-CAN2A-008 | test: (this)
    """
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(429), clock=clock)
    with pytest.raises(PartialSuiteError):
        execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2[:4],
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            max_retries=0,
            sleeper=clock,
        )
    assert len(provider.calls) == 4
    assert clock.seconds == []


# ---------------------------------------------------------------------------
# P6 -- the case the contract exists for
# ---------------------------------------------------------------------------


def test_p6_one_transient_prompt_still_yields_50() -> None:
    """P6/A5: 1 prompt 429s once then succeeds; 49 clean -> 50 results.

    This is the CAN-2a goal in one assertion: the leg that would have
    been discarded at 49/50 now completes, and PartialSuiteError is not
    raised.

    #SG-TRACE: REQ-CAN2A-010 | test: (this)
    """
    flaky = CANARY_SUITE_V2[17]
    clock = _FakeClock()
    provider = _ScriptedProvider(
        script={flaky["user"]: [_http(429)]}, clock=clock
    )

    results = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=False,
        provider=provider,
        suite_version=SUITE_VERSION_V2,
        delay_ms=100,
        sleeper=clock,
    )

    assert len(results) == 50
    assert [r.prompt_id for r in results] == [
        p["prompt_id"] for p in CANARY_SUITE_V2
    ]
    assert len(provider.calls) == 51  # one prompt was asked twice
    # 49 pacing sleeps of 100 ms + exactly one 5 s backoff.
    assert clock.ms.count(100.0) == 49
    assert clock.ms.count(float(RETRY_BACKOFF_BASE_MS)) == 1
    assert len(clock.seconds) == 50
    # The retry happened WITHIN the failing prompt's attempt: the
    # backoff sits between the two calls for that prompt.
    idx = [
        i
        for i, (_kind, arg) in enumerate(clock.events)
        if arg == flaky["user"]
    ]
    assert len(idx) == 2
    between = clock.events[idx[0] + 1 : idx[1]]
    assert between == [("sleep", RETRY_BACKOFF_BASE_MS / 1000.0)]


def test_a6_exhausted_retries_still_discard_the_whole_run() -> None:
    """A6/C5: discard-on-partial is unchanged by retrying.

    49 prompts answer perfectly and one 429s forever.  Retrying makes
    success more likely; it does not weaken the guarantee, so the run
    is still discarded with accurate completed/expected/failed data and
    nothing is staged for aggregation.

    #SG-TRACE: REQ-CAN2A-010 | test: (this)
    """
    doomed = CANARY_SUITE_V2[42]
    clock = _FakeClock()
    provider = _ScriptedProvider(
        script={doomed["user"]: [_http(429), _http(429), _http(429)]},
        clock=clock,
    )
    aggregator = Aggregator(_rng=random.Random(5))

    with pytest.raises(PartialSuiteError) as exc_info:
        results = execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2,
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            sleeper=clock,
        )
        for result in results:
            aggregator.add_result(result)

    exc = exc_info.value
    assert exc.completed == 49
    assert exc.expected == 50
    assert exc.failed_prompt_ids == [doomed["prompt_id"]]
    assert len(provider.calls) == 52  # 49 clean + 3 attempts on the doomed
    assert clock.ms == [5000.0, 10000.0]
    assert aggregator.pending_count(MODEL) == 0
    with pytest.raises(ValueError, match="No pending results"):
        aggregator.flush(MODEL)


# ---------------------------------------------------------------------------
# A7 -- structured status on the transport boundary
# ---------------------------------------------------------------------------


def test_provider_error_status_code_optional_and_defaults_none() -> None:
    """A7: the new attribute is optional and defaults to None.

    #SG-TRACE: REQ-CAN2A-001 | test: (this)
    """
    assert ProviderError("boom").status_code is None
    assert ProviderError("boom", status_code=429).status_code == 429
    assert ProviderError("boom", 503).status_code == 503
    assert isinstance(ProviderError("boom"), RuntimeError)
    assert str(ProviderError("boom", status_code=429)) == "boom"


def _transport_raising(exc: BaseException) -> Callable[..., object]:
    """urlopen replacement that raises *exc* on use."""

    def _open(*args: object, **kwargs: object) -> object:
        raise exc

    return _open


def test_transport_http_error_carries_structured_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A7: HTTP failures carry the status; everything else carries None.

    The message text is asserted to be unchanged from the pre-CAN-2a
    wording -- the status is now available structurally IN ADDITION to
    the string, so no caller ever needs to parse it.

    #SG-TRACE: REQ-CAN2A-002 | test: (this)
    """
    http_error = urllib.error.HTTPError(
        url="https://example.invalid/v1/chat/completions",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=None,
    )
    monkeypatch.setattr(
        "urllib.request.urlopen", _transport_raising(http_error)
    )
    with pytest.raises(ProviderError) as exc_info:
        _urllib_transport("https://example.invalid/v1", {}, b"{}", 1.0)
    assert exc_info.value.status_code == 429
    assert str(exc_info.value) == "provider HTTP 429"
    assert exc_info.value.status_code in TRANSIENT_STATUS_CODES

    monkeypatch.setattr(
        "urllib.request.urlopen",
        _transport_raising(urllib.error.URLError("timed out")),
    )
    with pytest.raises(ProviderError) as exc_info:
        _urllib_transport("https://example.invalid/v1", {}, b"{}", 1.0)
    assert exc_info.value.status_code is None
    assert "unreachable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# P8/A8 -- pacing budget against the GitHub Actions job timeout
# ---------------------------------------------------------------------------

# Recommended per-leg pacing for google/gemini-3.5-flash-lite.  The free
# tier's binding constraint is requests-per-minute: the unpaced run of
# 2026-07-31 completed 18 of 50 sequential calls before hard-failing,
# which is what a ~15 req/min quota looks like once the initial token
# bucket is drained.  4500 ms between prompts is 13.3 req/min -- about
# 11% under a 15 req/min quota, enough headroom for clock skew and for
# the retry attempts that also count against the quota.
GOOGLE_LEG_DELAY_MS: int = 4_500

# Budget for the wall-clock a paced leg may ADD (pacing + the retry
# ceiling), in seconds.
#
# .github/workflows/probe_weather.yml sets `timeout-minutes: 15` per
# matrix leg (the file is protected from remote writes; the per-leg
# SEISMOGRAPH_PROBE_DELAY_MS entry is applied by the maintainer).  A leg
# spends, before any pacing: ~60 s of checkout + setup-python + pip,
# up to ~110 s in the Render cold-start warm-up loop, and ~70 s of real
# provider latency (the mistral leg served 50 calls in 68 s on
# 2026-07-31).  That is ~4 minutes of non-pacing work, so capping the
# ADDED time at 5 minutes keeps a fully-paced leg at ~9 minutes and
# leaves >=6 minutes of headroom inside the 15-minute timeout.
PACING_BUDGET_S: float = 300.0
ACTIONS_JOB_TIMEOUT_S: float = 15 * 60
ACTIONS_FIXED_OVERHEAD_S: float = 60.0 + 110.0  # setup + gateway warm-up
OBSERVED_SUITE_LATENCY_S: float = 70.0  # mistral: 50 calls in 68 s


def test_p8_google_leg_pacing_budget_fits_actions_timeout() -> None:
    """P8/A8/R1: the google setting is computed and bounded, not hoped.

    The added wall-clock is measured on a real 50-prompt run through
    the injected clock (not asserted from prose), then checked against
    PACING_BUDGET_S and against the whole 15-minute job.

    #SG-TRACE: REQ-CAN2A-006 | test: (this)
    """
    clock = _FakeClock()
    results = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=True,
        suite_version=SUITE_VERSION_V2,
        delay_ms=GOOGLE_LEG_DELAY_MS,
        sleeper=clock,
    )
    assert len(results) == 50

    measured_s = clock.total_s
    assert measured_s == pytest.approx(49 * 4.5)
    assert measured_s == pytest.approx(220.5)

    # Worst case adds the run-wide retry ceiling on top.
    worst_case_s = pacing_budget_ms(50, GOOGLE_LEG_DELAY_MS) / 1000.0
    assert worst_case_s == pytest.approx(220.5 + 60.0)
    assert measured_s < worst_case_s <= PACING_BUDGET_S

    # ... and the whole leg still fits the job timeout with headroom.
    leg_s = worst_case_s + ACTIONS_FIXED_OVERHEAD_S + OBSERVED_SUITE_LATENCY_S
    assert leg_s < ACTIONS_JOB_TIMEOUT_S
    assert ACTIONS_JOB_TIMEOUT_S - leg_s > 5 * 60

    # The pacing keeps the leg under a 15 req/min free-tier quota.
    requests_per_minute = 60_000 / GOOGLE_LEG_DELAY_MS
    assert requests_per_minute == pytest.approx(13.333, abs=0.001)
    assert requests_per_minute < 15

    # The budget has teeth: a naive "one minute between prompts" leg,
    # or a 10 s delay, blows it.
    assert pacing_budget_ms(50, 10_000) / 1000.0 > PACING_BUDGET_S
    assert pacing_budget_ms(50, 60_000) / 1000.0 > ACTIONS_JOB_TIMEOUT_S

    # An unpaced leg (mistral, openai, anthropic) adds only the retry
    # ceiling, so CAN-2a costs those legs nothing when nothing fails.
    assert pacing_budget_ms(50, 0) == DEFAULT_MAX_TOTAL_BACKOFF_MS


def test_pacing_budget_ms_edges() -> None:
    """The budget helper is total, not per-prompt, and never negative.

    #SG-TRACE: REQ-CAN2A-006 | test: (this)
    """
    assert pacing_budget_ms(0, 5_000, max_total_backoff_ms=0) == 0
    assert pacing_budget_ms(1, 5_000, max_total_backoff_ms=0) == 0
    assert pacing_budget_ms(2, 5_000, max_total_backoff_ms=0) == 5_000
    assert pacing_budget_ms(50, 250, max_total_backoff_ms=0) == 49 * 250
    assert pacing_budget_ms(50, -1, max_total_backoff_ms=-1) == 0


# ---------------------------------------------------------------------------
# ADV-1 -- retries must not become an emission amplifier
# ---------------------------------------------------------------------------


class _RecordingGateway:
    """Stand-in for the gateway: counts batches that reach ingestion."""

    def __init__(self) -> None:
        self.batches: list[object] = []

    def ingest(self, batch: object) -> None:
        self.batches.append(batch)


def _attempt_emission(
    gateway: _RecordingGateway,
    provider: _ScriptedProvider,
    clock: _FakeClock,
    max_retries: int,
) -> int:
    """One live_emit-shaped cycle; returns the process exit code.

    Mirrors scripts/live_emit.main(): run the strict suite, and only on
    a complete run aggregate and emit.  A PartialSuiteError means
    nothing is staged and nothing is emitted.
    """
    aggregator = Aggregator(_rng=random.Random(2))
    try:
        results = execute_canary_strict(
            MODEL,
            suite=CANARY_SUITE_V2,
            mock=False,
            provider=provider,
            suite_version=SUITE_VERSION_V2,
            delay_ms=250,
            max_retries=max_retries,
            sleeper=clock,
        )
    except PartialSuiteError:
        assert aggregator.pending_count(MODEL) == 0
        return 1
    for result in results:
        aggregator.add_result(result)
    gateway.ingest(aggregator.flush(MODEL, fleet_id=None))
    return 0


def test_adv1_always_429_emits_zero_batches_and_cannot_promote() -> None:
    """ADV-1: a rate-limited provider is silent, not loud.

    Two properties, both required by the contract:

    1. No amplification.  Five emission cycles against a provider that
       always 429s produce ZERO batches at the gateway -- exactly as
       many as the pre-CAN-2a configuration (max_retries=0) produces.
       Retrying cannot turn a partial leg into a partial batch, because
       the retry lives INSIDE a prompt attempt and the all-or-nothing
       gate is unchanged.
    2. No cheaper quorum.  Even if the retry cycles were somehow turned
       into drift candidates, the real AgreementScorer still refuses to
       promote them: one org, q(M=1) = 3 distinct orgs required.

    #SG-TRACE: REQ-CAN2A-010, REQ-ENGINE-008 | test: (this)
    """
    cycles = 5
    gateway = _RecordingGateway()
    clock = _FakeClock()
    provider = _ScriptedProvider(always=lambda: _http(429), clock=clock)
    for _ in range(cycles):
        assert (
            _attempt_emission(gateway, provider, clock, DEFAULT_MAX_RETRIES)
            == 1
        )
    assert gateway.batches == []

    # The same scenario with retrying switched off -- i.e. exactly
    # today's behaviour -- emits the same number of batches: zero.
    today_gateway = _RecordingGateway()
    today_clock = _FakeClock()
    today_provider = _ScriptedProvider(
        always=lambda: _http(429), clock=today_clock
    )
    for _ in range(cycles):
        assert (
            _attempt_emission(today_gateway, today_provider, today_clock, 0)
            == 1
        )
    assert today_gateway.batches == gateway.batches == []
    # Retrying costs extra provider calls but buys no extra emissions.
    assert len(provider.calls) > len(today_provider.calls)
    assert len(today_provider.calls) == cycles * 50

    # Per-cycle backoff never exceeded the run-wide ceiling.
    per_cycle_backoff_ms = (sum(clock.ms) - cycles * 49 * 250.0) / cycles
    assert per_cycle_backoff_ms <= DEFAULT_MAX_TOTAL_BACKOFF_MS

    # A single org cannot promote a public alert, however many retry
    # cycles it performed.
    scorer = AgreementScorer()
    for cycle in range(cycles * (1 + DEFAULT_MAX_RETRIES)):
        scorer.ingest(
            ChangePointResult(
                model_tuple=MODEL,
                change_detected=True,
                score=9.9,
                threshold=5.0,
                contributing_orgs=["org-rate-limited"],
                metric_name="avg_output_length",
                timestamp_ns=cycle * 1_000_000_000,
            )
        )
    assert required_quorum(1) == 3
    assert (
        scorer.promote_to_public_alert(
            MODEL,
            "avg_output_length",
            now_ns=cycles * (1 + DEFAULT_MAX_RETRIES) * 1_000_000_000,
        )
        is None
    )


# ---------------------------------------------------------------------------
# ADV-2 -- pacing must not mask (or manufacture) semantic drift
# ---------------------------------------------------------------------------


class _FixtureProvider:
    """Deterministic provider: one frozen response per prompt.

    ``shifted`` moves ONLY semantic features (the multilingual answers
    collapse to a stub, the reasoning_length prompts lose their
    reasoning budget).  Latency is a pure function of the prompt index
    in both variants, so a latency/uptime monitor sees nothing -- the
    ADV-2 scenario of test_canary_suite_v2.
    """

    STABLE_REASONING_TOKENS = 900
    BASE_REASONING_TOKENS = 40
    SHIFTED_STUB = "n/a"

    def __init__(self, shifted: bool = False) -> None:
        self.shifted = shifted
        self.calls = 0
        self._index = {
            p["user"]: (i, p) for i, p in enumerate(CANARY_SUITE_V2)
        }

    def complete_ex(
        self,
        model: str,
        system: str,
        user: str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        self.calls += 1
        index, prompt = self._index[user]
        pid = prompt["prompt_id"]
        category = prompt["category"]
        reasoning = self.BASE_REASONING_TOKENS
        if category == "reasoning_length":
            reasoning = 0 if self.shifted else self.STABLE_REASONING_TOKENS
        text = _mock_text_for(pid)
        if self.shifted and category == "multilingual":
            text = self.SHIFTED_STUB
        if category == "tool_calling":
            return CompletionResult(
                text="",
                tool_calls_json=_mock_tool_calls_for(pid),
                output_tokens=48,
                reasoning_tokens=reasoning,
                latency_ms=400 + (index % 7) * 13,
            )
        return CompletionResult(
            text=text,
            tool_calls_json=None,
            output_tokens=48,
            reasoning_tokens=reasoning,
            latency_ms=400 + (index % 7) * 13,
        )


def _raw_mean(results: list[CanaryResult], attr: str) -> float:
    """Undoised mean of one per-record feature."""
    return sum(getattr(r, attr) or 0 for r in results) / len(results)


def _metrics_of(results: list[CanaryResult], seed: int) -> tuple[dict, dict]:
    """DP-noised metrics + canary hashes, under a fixed noise seed."""
    aggregator = Aggregator(_rng=random.Random(seed))
    for result in results:
        aggregator.add_result(result)
    batch = aggregator.flush(MODEL, fleet_id=None)
    return dict(batch.metrics), dict(batch.canary_hashes)


def _run_fixture(shifted: bool, delay_ms: int) -> tuple:
    """Run the fixture suite paced or unpaced; return (results, clock)."""
    clock = _FakeClock()
    provider = _FixtureProvider(shifted=shifted)
    results = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=False,
        provider=provider,
        suite_version=SUITE_VERSION_V2,
        delay_ms=delay_ms,
        sleeper=clock,
    )
    assert provider.calls == 50
    return results, clock


def test_adv2_paced_and_unpaced_metrics_are_identical() -> None:
    """ADV-2: pacing changes timing only, never features.

    Over the SAME fixture responses, a paced run (delay 4500 ms, the
    google setting) and an unpaced run produce byte-identical derived
    features, identical DP-noised metrics under the same noise seed,
    and identical canary hashes.  The only difference between the two
    runs is the fake clock: 49 sleeps vs none.

    The semantic-drift half is then asserted on top: the metric DELTA
    produced by a semantic-only shift is the same whether the run was
    paced or not, so pacing can neither mask a provider change nor
    manufacture one.

    #SG-TRACE: REQ-CAN2A-007 | test: (this)
    """
    stable_unpaced, clock_unpaced = _run_fixture(False, 0)
    stable_paced, clock_paced = _run_fixture(False, GOOGLE_LEG_DELAY_MS)

    # 1. Timing differs...
    assert clock_unpaced.seconds == []
    assert len(clock_paced.seconds) == 49
    assert clock_paced.total_s == pytest.approx(220.5)

    # 2. ... and nothing else does.
    assert _features(stable_paced) == _features(stable_unpaced)
    assert _metrics_of(stable_paced, 17) == _metrics_of(stable_unpaced, 17)

    # 3. A semantic-only shift is seen identically through both.
    shifted_unpaced, _ = _run_fixture(True, 0)
    shifted_paced, _ = _run_fixture(True, GOOGLE_LEG_DELAY_MS)
    assert _features(shifted_paced) == _features(shifted_unpaced)
    assert _metrics_of(shifted_paced, 17) == _metrics_of(shifted_unpaced, 17)

    metrics_stable, _ = _metrics_of(stable_paced, 17)
    metrics_shifted, _ = _metrics_of(shifted_paced, 17)
    metrics_stable_u, _ = _metrics_of(stable_unpaced, 17)
    metrics_shifted_u, _ = _metrics_of(shifted_unpaced, 17)
    delta_paced = {
        k: metrics_stable[k] - metrics_shifted[k] for k in metrics_stable
    }
    delta_unpaced = {
        k: metrics_stable_u[k] - metrics_shifted_u[k] for k in metrics_stable_u
    }
    assert delta_paced == delta_unpaced

    # The shift really is visible (otherwise the equality above would
    # be a vacuous "nothing moved in either run").  The RAW feature
    # delta is exact; the DP-noised delta is only required to keep its
    # sign, because the noised value of the shifted window can hit the
    # non-negativity clamp.
    raw_delta = _raw_mean(stable_paced, "reasoning_tokens") - _raw_mean(
        shifted_paced, "reasoning_tokens"
    )
    assert raw_delta == pytest.approx(
        8 * _FixtureProvider.STABLE_REASONING_TOKENS / 50
    )
    assert raw_delta == pytest.approx(144.0)
    assert delta_paced["avg_reasoning_tokens"] > 0
    assert delta_paced["avg_output_length"] > 0
    assert delta_paced["result_count"] == 0.0


def test_adv2_retry_does_not_alter_features() -> None:
    """ADV-2 corollary: a retried prompt contributes its normal record.

    A prompt that 429s once and then answers must produce exactly the
    record the same prompt produces when it answers first time -- a
    retry is a repeated request, not a different measurement.

    #SG-TRACE: REQ-CAN2A-007 | test: (this)
    """
    clean, _ = _run_fixture(False, 0)

    clock = _FakeClock()
    provider = _FixtureProvider(shifted=False)
    flaky_user = CANARY_SUITE_V2[23]["user"]
    pending = [_http(429)]
    inner = provider.complete_ex

    def _flaky_complete_ex(model, system, user, tools=None, max_tokens=None):
        if user == flaky_user and pending:
            pending.pop()
            raise _http(429)
        return inner(model, system, user, tools=tools, max_tokens=max_tokens)

    provider.complete_ex = _flaky_complete_ex  # type: ignore[method-assign]
    retried = execute_canary_strict(
        MODEL,
        suite=CANARY_SUITE_V2,
        mock=False,
        provider=provider,
        suite_version=SUITE_VERSION_V2,
        sleeper=clock,
    )

    assert clock.ms == [float(RETRY_BACKOFF_BASE_MS)]
    assert _features(retried) == _features(clean)
    assert _metrics_of(retried, 17) == _metrics_of(clean, 17)


# ---------------------------------------------------------------------------
# C2 -- scripts/live_emit.py environment pass-through
# ---------------------------------------------------------------------------


def test_live_emit_reads_pacing_env_and_passes_it_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2: SEISMOGRAPH_PROBE_DELAY_MS / _MAX_RETRIES reach the runner.

    The runner is stubbed to capture its keyword arguments and then
    raise PartialSuiteError, so main() returns 1 without touching the
    network.

    #SG-TRACE: REQ-CAN2A-011 | test: (this)
    """
    captured: dict = {}

    def _fake_strict(*args: object, **kwargs: object) -> list:
        captured.update(kwargs)
        raise PartialSuiteError(0, 50, [])

    monkeypatch.setattr(live_emit, "execute_canary_strict", _fake_strict)

    # Defaults: no pacing, the runner's own retry default.
    monkeypatch.delenv("SEISMOGRAPH_PROBE_DELAY_MS", raising=False)
    monkeypatch.delenv("SEISMOGRAPH_PROBE_MAX_RETRIES", raising=False)
    assert live_emit.main() == 1
    assert captured["delay_ms"] == 0
    assert captured["max_retries"] == DEFAULT_MAX_RETRIES

    # Configured per leg by the workflow matrix.
    captured.clear()
    monkeypatch.setenv("SEISMOGRAPH_PROBE_DELAY_MS", str(GOOGLE_LEG_DELAY_MS))
    monkeypatch.setenv("SEISMOGRAPH_PROBE_MAX_RETRIES", "3")
    assert live_emit.main() == 1
    assert captured["delay_ms"] == GOOGLE_LEG_DELAY_MS
    assert captured["max_retries"] == 3
    # The suite and version passed through are still the v2.0.0 ones.
    assert captured["suite"] is CANARY_SUITE_V2
    assert captured["suite_version"] == SUITE_VERSION_V2
    assert captured["mock"] is False
