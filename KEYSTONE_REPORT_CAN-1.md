# KEYSTONE REPORT (DRAFT, unsigned) — SG-FEAT-TOOLCALL-001 + SG-FEAT-TOKENS-001

Date: 2026-07-24 | Status: draft for review | Contract: /tmp/agents/engine/CONTRACT.md

## What

Two probe-side features; engine/ untouched (frozen), gateway change additive-only.

1. **Tool-calling canaries (Feature A).** New `tool_calling` category:
   suite v1.1.0 = frozen v1.0.0 corpus + one canary that sends a fixed
   OpenAI-compatible `tools` request (frozen `get_weather` schema,
   temperature 0, max_tokens 64). Per-canary boolean
   `tool_call_valid` = "response contained a tool call that parses and
   validates against the frozen JSON schema" (minimal stdlib validator:
   name, required, types, enum, additionalProperties). Aggregated as
   DP-noised `tool_call_validity_rate` (Δf = 1/n, ε = 2.0, clamped [0,1]).
   Suite content-addressing extended: `suite_content_hash(prompts, tools)`
   folds the tool schema into the SHA-256 version hash.
2. **Reasoning-token metric (Feature B).** Provider layer gains
   `complete_ex(...)` (backward-compatible; `complete()` signature and
   error behavior frozen) which None-safely captures
   `usage.completion_tokens` and
   `usage.completion_tokens_details.reasoning_tokens`. Per-canary
   `output_tokens` / `reasoning_tokens` flow through CanaryResult (and the
   ProbeSDK OTel span path via `gen_ai.usage.*` attributes) into the
   Aggregator, emitted as `avg_output_tokens` / `avg_reasoning_tokens`
   with the standard DP treatment (None→0, clamp [0, 8192], Laplace
   Δf = 8192/n).

New metrics are emitted **conditionally** (only when the batch actually
contains tool/token data), so legacy batches keep the exact legacy metric
key set.

## Why (market-driven)

Tool/function calling is the dominant production integration surface;
silent tool-schema drift breaks agent pipelines with zero latency/uptime
signal. Reasoning-token counts are the leading cost/behavior indicator for
reasoning-mode models. Both are cheap scalars fully inside the existing
privacy envelope.

## Evidence

- Baseline gate before changes: 151 passed; `ruff check .` and
  `ruff format --check .` clean.
- Final gate: **193 passed** (151 old + 42 new), 0 failed;
  `ruff check .` clean; `ruff format --check .` clean (56 files).
- Adversarial (a) — poisoned/Sybil probe:
  `test_sybil_single_client_new_metrics_no_public_alert` — a single
  client_id flooding drifted `tool_call_validity_rate`/`avg_reasoning_tokens`
  fires local CUSUM alerts but produces zero PublicDriftAlerts; weather
  stays STABLE (quorum gate unchanged, keyed on distinct orgs per
  (model_tuple, metric_name)). `test_sybil_cannot_smuggle_raw_text_via_new_metrics`
  — allowlist stays closed; non-numeric values 422.
- Adversarial (b) — silent semantic/schema shift:
  `test_adversarial_schema_shift_caught_by_tool_validity` — provider
  renames the required `unit` argument to `units` with identical latency,
  no error, unchanged json_success signal; `tool_call_valid` flips
  True→False and the raw batch rate drops 0.25→0.0, exactly the stream
  CUSUM consumes.
- Privacy: no raw text/tool arguments leave the probe
  (`test_no_raw_tool_output_leaves_probe`); all new metrics ride the
  existing Aggregator.flush → DPAccountant path; no new outbound object.

## Files changed

probe/providers.py, probe/canary.py, probe/privacy.py, probe/sdk.py,
gateway/schema.py (additive allowlist), + tests/test_tool_canary.py,
tests/test_token_metrics.py. Full copies in patch/. Trace comments
#SG-TRACE: REQ-TOOLCAN-001..021, REQ-TOKMET-001..011, REQ-GW-030.

## Compatibility caveats

1. **Gateway metric allowlist**: `gateway/schema.py::_ALLOWED_METRIC_KEYS`
   is strict; extended additively (+ probe-side mirror
   `SignalBatch._METRIC_KEYS`). A NEW probe emitting new metrics against
   an OLD (un-upgraded) gateway would be 422-rejected — deploy gateway
   first; conditional emission confines exposure to probes actually
   running suite v1.1 / usage-reporting providers.
2. engine/ frozen: new metrics feed the live CUSUM detector generically
   but are not persisted as DB columns by engine/repository.save_batch
   and not re-warmed by bootstrap_detector after a gateway restart
   (baseline re-accumulates from live traffic; same limitation class as
   Phase 2 for any non-column metric).
3. `avg_output_tokens`: probes that already set the
   `gen_ai.usage.output_tokens` span attribute will start emitting this
   key after upgrade (accepted by the upgraded gateway).

— unsigned draft; requires maintainer signature before release —
