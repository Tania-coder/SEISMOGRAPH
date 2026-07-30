# SEISMOGRAPH — Detection Methodology

**Frozen 2026-07-30.** Every parameter below was committed to the public
repository *before* any live drift alert was issued. That ordering is the
point of this document: a detector whose thresholds can be tuned after
seeing the data is not evidence of anything.

Repository: https://github.com/Tania-coder/SEISMOGRAPH · Apache-2.0 ·
DOI [10.5281/zenodo.21045517](https://doi.org/10.5281/zenodo.21045517)

---

## 1. What is being measured

SEISMOGRAPH does not measure whether a model is *good*. It measures whether
a model's behaviour **changed**, against its own past, on a fixed corpus.

A probe runs an immutable set of prompts against a provider endpoint at
temperature 0, derives a small number of numeric features from the responses,
adds calibrated noise, and transmits only those numbers. The raw prompts and
raw model outputs never leave the probe process.

---

## 2. The canary corpus

| | |
|---|---|
| Current suite | **v2.0.0** |
| Content hash | `d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14` |
| Prompts | **50** |
| Temperature | 0 |
| Hard cap | 200 prompts (`REQ-CANARY-002`) |

Composition:

| Category | Prompts | What drift in it looks like |
|---|---|---|
| `logic_reasoning` | 9 | answers to deterministic puzzles change |
| `structured_output` | 9 | JSON stops parsing, or gains prose/fences |
| `refusal_tone` | 8 | new hedging or refusal on legitimate professional questions |
| `tool_calling` | 8 | tool calls stop validating against a frozen schema |
| `reasoning_length` | 8 | internal reasoning budget shifts |
| `multilingual` | 8 | non-English output degrades independently of English |

**Content addressing.** The suite hash is SHA-256 over the canonical JSON of
the ordered prompt corpus *and* the frozen tool schemas. Changing a single
character of a single prompt, reordering the list, or altering a tool
definition produces a different hash and therefore a different suite version.

**Append-only.** A new suite version may only add prompts. Suite v2.0.0 is
`v1.1.0 + 46`, and the four v1.1.0 entries are byte-identical. Historical
corpora are never mutated.

**Suite versions are not comparable.** Baselines, change-point streams and
cross-organisation agreement are all scoped by suite version. Observations
made under different corpora are never mixed and never counted as agreement.

### Prior versions

| Version | Prompts | Content hash |
|---|---|---|
| v1.1.0 | 4 | `62422b5875d6ec785829d715f7155305cb322bb0a85c5525ab73f20bf86808c8` |
| v1.0.0 | 3 | superseded |

---

## 3. Emitted features

Per flush, each metric is a mean over the `n` results in that window.

| Metric | Domain | Meaning |
|---|---|---|
| `avg_output_length` | characters, clamped [0, 8192] | response length |
| `json_success_rate` | [0, 1] | fraction of responses parsing as JSON |
| `tool_call_validity_rate` | [0, 1] | fraction of tool calls validating against the frozen schema |
| `avg_output_tokens` | clamped [0, 8192] | provider-reported completion tokens |
| `avg_reasoning_tokens` | clamped [0, 8192] | provider-reported reasoning tokens |
| `result_count` | integer | `n`, transmitted in the clear |

Also transmitted: a SHA-256 hash per prompt id, the model tuple
(`provider/model@version`), the suite version, and the window bounds.

**Never transmitted:** prompt text, response text, or anything from which
either can be reconstructed.

### Known limitation, stated up front

`avg_output_length` declares a clamp of 8192 characters, while the probe
caps generation at 64 tokens (~256 characters). Differential-privacy noise
is scaled by the *declared* clamp, so this metric currently carries roughly
32x more noise than its own wire contract requires and is **not a reliable
drift signal at present**. It is retained for continuity and is tracked as a
known defect (PRIV-011). Claims made from live data will not rest on it.
The metric that carries reasoning-budget drift today is
`avg_reasoning_tokens`, which is not bounded by the generation cap.

---

## 4. Differential privacy

| | |
|---|---|
| Mechanism | Laplace |
| Epsilon per flush | **2.0** |
| Sensitivity | `delta_f = MAX / n` (substitution DP on a bounded mean, `n` public) |
| Noise scale | `b = delta_f / epsilon` |
| Daily budget | **10.0** per probe per model tuple, rolling 24 h |
| Max flushes/day | 5 (`10.0 / 2.0`), enforced; exceeding it puts the probe to sleep |

Composition is sequential: `epsilon_total = sum(epsilon per flush)`.
Collection may run more often than transmission; only transmission spends
epsilon.

Because sensitivity is `MAX/n`, a larger corpus reduces noise proportionally.
Moving from `n=4` to `n=50` cut the Laplace scale by 12.5x. It does not
dilute a single-prompt shift: signal (`Delta/n`) and DP noise (`~1/n`) scale
together, so the DP-limited component of signal-to-noise is invariant in `n`,
while sampling noise falls as `1/sqrt(n)`.

---

## 5. Change-point detection

Two-sided CUSUM, one independent stream per
`(model_tuple, suite_version, metric_name)`.

| Parameter | Value |
|---|---|
| Decision interval `h` | **5.0** (in standard deviations) |
| Reference value `k` | **0.5** |
| Baseline samples | **30** before any alert is possible |
| Nominal ARL0 | ~500 |

Each stream normalises against its own baseline, so no absolute threshold is
carried across models or metrics. A stream that has not yet accumulated 30
observations cannot alert at all.

**Probe cadence.** 5 flushes/day during a baseline warm-up (the budget
ceiling), 2/day in steady state. Sustained cadence above ~1.5
flushes/day/metric pressures the candidate TTL toward its false-positive
ceiling once multiple organisations feed the quorum, so the warm-up rate is
used only while a single organisation is observing.

---

## 6. From a local candidate to a public alert

A CUSUM crossing is a **candidate**, not an alert. It is private to the
organisation that produced it.

A candidate is promoted to a public drift alert only when independent
organisations agree, on the same `(model_tuple, suite_version, metric_name)`
stream, within the candidate lifetime:

```
q(M) = max(3, ceil(M / 3))
```

where `M` is the live observer population on that stream.

| Constant | Value |
|---|---|
| Quorum floor | **3** distinct organisations |
| Fraction | 1/3 |
| Candidate TTL | **14 days** (event-time) |

The floor of 3 exists for Sybil resistance, not for false-positive control.
The 1/3 slope was derived from an explicit power/false-positive model rather
than chosen for convenience: with an exact binomial model anchored to the
live detector's ARL0, the binding constraint was shown to be detection
**power**, not false positives — a majority rule suppressed false positives
by 5-10 orders of magnitude while eroding the ability to detect anything.
The schedule is flat at `q=3` for `M <= 9`, with a knee at `M = 10`.

**Consequence, stated plainly: a single organisation can never produce a
public drift alert, no matter how strong its signal.** Single-org signals are
private fleet data. This is the property that makes the public board
resistant to a poisoned or duplicated probe, and it is enforced by test, not
by policy.

---

## 7. Validation

**Reproducible backtest.** Against the Anthropic incident of 2025-09-17 — a
postmortem describing three infrastructure bugs, explicitly *not* a model
update — a seeded backtest (`SEED=42`) on
`anthropic/claude-sonnet-4@global` first alerts on **2025-08-10**, a lead of
**38 days over the postmortem** and 19 days over the escalation.

This is a backtest, not a live catch. It demonstrates that the method would
have flagged the behavioural change from public evidence at a point when the
provider's own status page showed nothing. No live drift alert has been
issued by the public network to date.

**Adversarial testing.** Two failure modes are tested on every change to the
detection path: a poisoned or Sybil probe injecting fabricated drift, and a
provider-side change that produces no latency or uptime signal while shifting
semantic output. Both are required to pass before any detection change ships.

**Test suite.** 257 tests on `main`, run in CI on every push, alongside CodeQL
static analysis.

---

## 8. What this method cannot do

- It cannot attribute a change to a cause. A detected shift may be a model
  update, an infrastructure bug, a routing change, or a serving-stack
  regression. The 2025 incident it was validated against was infrastructure.
- It cannot detect drift confined to behaviour the corpus does not probe.
- It cannot alert publicly below three independent observers.
- It cannot alert at all on a stream with fewer than 30 observations.
- Absolute metric levels are not comparable across providers; only a
  stream's change against its own history is meaningful.

---

## 9. Changing any of this

Detection parameters are constants in the repository, not runtime
configuration. Changing `h`, `k`, `baseline_samples`, epsilon, the clamps,
the quorum schedule or the TTL requires a commit, and the commit history is
public. A parameter change after an alert is visible to anyone who looks.

| Parameter | Source |
|---|---|
| `h`, `k`, `baseline_samples` | `gateway/main.py`, `engine/detector.py` |
| `EPSILON`, clamps, budget | `probe/privacy.py` |
| `QUORUM_FLOOR`, `QUORUM_FRAC_*`, TTL | `engine/correlation.py` |
| Canary corpus | `probe/canary.py` |
