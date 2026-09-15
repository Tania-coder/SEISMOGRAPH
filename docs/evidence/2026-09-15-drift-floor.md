<!--
SEISMOGRAPH -- Evidence: determinism floor and model-distance measurement
Copyright 2026 Tatiana Radchenko (tatyan.radchenko@gmail.com)
Licensed under the Apache License, Version 2.0, as part of the
SEISMOGRAPH project. See LICENSE and COPYRIGHT at the repository root.
-->

# Determinism floor and model distance, measured

| | |
|---|---|
| Author | Tatiana Radchenko -- Independent, Aarhus, Denmark |
| Measured | 2026-09-14T22:32Z to 2026-09-15T00:00Z |
| Instrument | `scripts/measure_drift_floor.py` |
| Raw data | `docs/evidence/driftfloor/run_*.csv` (7 runs, 350 calls) |
| Provider | Google, OpenAI-compatible endpoint |
| Suite | `CANARY_SUITE_V2`, 50 prompts, temperature 0, max_tokens 128 |

Everything below is measured and recomputable from the CSVs in this
directory with a stdlib Python and no other part of this repository.

## Why

The project's public story rested on one third-party incident. The
question "does this problem exist for anyone other than the provider it
happened to" had no answer of our own. This measurement produces one.

It asks two things:

1. How much does an endpoint's output move when **nothing** changed?
   Without that floor, no statement about drift means anything.
2. Is that floor smaller than the distance between two models?

## Method

Seven runs of the same frozen 50-prompt suite at temperature 0:

| label | model | note |
|---|---|---|
| a1, a2, a3 | `gemini-3.5-flash-lite` | pinned, the production leg |
| b1, b2 | `gemini-flash-lite-latest` | a moving alias |
| c1, c2 | `gemini-3.1-flash-lite` | pinned, previous generation |

Each response is reduced to a SHA-256 hash and a character count; raw
output is never stored. Two runs are compared on the prompt ids that
succeeded in **both**, and every rate is printed with its denominator.

`tool_calling` prompts (8 of 50) are **excluded from every rate**. The
tool-call JSON carries a per-call random id, and that id is inside the
hashed string, so a tool canary can never match itself. Evidence: across
a1/b1, 7 of 8 tool answers had byte-identical output length and 0 of 8
matched by hash. This contamination also exists in `probe/canary.py`,
which hashes `tool_calls_json` the same way -- a separate open defect.

## Result 1 -- the older model is deterministic, the newer one is not

Within a model, nothing changed between runs:

| pair | model | identical | rate | mean length delta |
|---|---|---|---|---|
| a1 vs a2 | 3.5-flash-lite | 26/41 | 63.4% | +1.8% |
| a1 vs a3 | 3.5-flash-lite | 25/42 | 59.5% | -0.9% |
| a2 vs a3 | 3.5-flash-lite | 25/41 | 61.0% | -2.6% |
| b1 vs b2 | flash-lite-latest | 21/42 | 50.0% | +1.8% |
| **c1 vs c2** | **3.1-flash-lite** | **42/42** | **100.0%** | **0.0%** |

`gemini-3.1-flash-lite` returns byte-identical answers on every
comparable prompt, in every category. `gemini-3.5-flash-lite`, same
provider and same settings, agrees with itself about 60% of the time.

The 100% row is also the instrument's **positive control**: the harness
can measure perfect agreement, so the ~60% is a property of the model
and not of the measurement.

Practical consequence: reproducibility is something a team can lose
silently by upgrading. Snapshot tests that pass on the old model go
flaky on the new one; a cache keyed on response hash loses its hit
rate; an exact-match eval quietly becomes noise.

## Result 2 -- the alias is not distinguishable from the pinned model

All six cross pairs of pinned 3.5 against the alias:

| | rate | mean length delta |
|---|---|---|
| within pinned 3.5 (3 pairs) | 59.5 - 63.4% | -2.6 to +1.8% |
| **pinned vs alias (6 pairs)** | **57.1 - 64.3%** | **-1.5 to +2.9%** |

The cross-model range sits inside the within-model range on both
measures. **On this date, the alias behaves like the pinned version and
the difference is not measurable.** That is a negative result and is
reported as one. It says nothing about tomorrow, and there is no
notification when it stops being true.

## Result 3 -- a generation change separates cleanly, but only on length

| | rate | mean length delta |
|---|---|---|
| within-model floor | 50.0 - 100.0% | -2.6 to +1.8% |
| pinned vs alias | 57.1 - 64.3% | -1.5 to +2.9% |
| **pinned vs previous generation** | **41.5 - 45.2%** | **-25.3 to -23.2%** |

Hash agreement does **not** separate the floor from the alias: both land
in the 50-64% band. Mean output length does, with no overlap at all:
everything that is the same model stays within +/-3%, and the
generation change is -24%.

This is the methodological finding. An exact-match fingerprint is the
obvious way to detect that a model moved, and it is the wrong one. A
distributional feature carries the signal. The gateway's change-point
detector already runs on `avg_output_length` and `json_success_rate`
rather than on hashes; this measurement is the first evidence from this
project that the choice was correct.

## A conclusion this data killed

An earlier reading of runs a1/b1/c1 alone suggested that stability was a
property of the prompt **category** -- `structured_output` looked stable
and `refusal_tone` looked useless as a canary, 0/8 in every comparison.

The c-group refutes it. On `gemini-3.1-flash-lite`, `refusal_tone` is
**8/8 identical**. The category is perfectly stable on one model and
perfectly unstable on another. Instability is a property of the
**model**, not of the task. The earlier reading was wrong and is
withdrawn.

## Limitations, stated rather than buried

1. One provider, one model family, one evening. Nothing here generalises
   to OpenAI, Anthropic or anyone else without being measured there.
2. `max_tokens=128` truncates long answers, which can only **inflate**
   agreement. The floor measured here is an upper bound on agreement,
   i.e. the real models may be less reproducible than shown.
3. The alias group has a single within-pair (b1 vs b2). Its 50.0% floor
   rests on one observation and should not be quoted as a rate on its own.
4. Run a2 exists once; an earlier a2 was destroyed by the instrument
   overwriting an identical `--label`. That defect is fixed (the runner
   now refuses and exits 3), but the lost run is not recoverable and its
   summary survives only as terminal output: 50/50 ok, mean length 184.70.
5. One prompt in a2 failed with a provider 503 and is excluded from
   comparisons involving a2; `n` is printed on every line.
6. `reasoning_length` answers are 1-5 characters long, so its 8/8 tells
   us nothing about stability and is not used in any conclusion.

## Reproduce

    python scripts/measure_drift_floor.py run --model-tuple google/<model> \
        --base-url https://generativelanguage.googleapis.com/v1beta/openai \
        --label <label> --out docs/evidence/driftfloor

    python scripts/measure_drift_floor.py compare \
        --a docs/evidence/driftfloor/run_a1.csv \
        --b docs/evidence/driftfloor/run_c1.csv

`compare` imports nothing from this repository, so the published CSVs
can be checked by anyone with a standard Python.
