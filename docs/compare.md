# `seismograph compare` — old model vs new model on your own prompts

Run your own prompts against two models, several times each, and get one
local page that says what changes if you switch, plus a dated evidence
file. Nothing leaves your machine except the calls to the two endpoints
you configure.

## Run

```
python -m probe.compare --suite my_prompts.jsonl --a openai/gpt-4o --b openai/gpt-5-mini --repeats 3
```

The first run prints the number of calls (items × repeats × 2) and sends
nothing. Add `--yes` to make the calls.

Output: `compare-<timestamp>/report.html` and `evidence.json`, plus the
SHA-256 of `evidence.json` printed at the end.

### Endpoints and keys

Per side, from the environment:

| variable | meaning |
|---|---|
| `SEISMOGRAPH_A_BASE_URL` / `SEISMOGRAPH_B_BASE_URL` | OpenAI-compatible root, e.g. `https://api.mistral.ai/v1`. Defaults exist for `openai` and `mistral`. |
| `SEISMOGRAPH_A_API_KEY` / `SEISMOGRAPH_B_API_KEY` | Bearer key. Never printed or written. |

### Options

| option | default | |
|---|---|---|
| `--repeats` | 3 | 2..5. Each item is asked this many times per model. |
| `--max-tokens` | 512 | per answer |
| `--delay-ms-a`, `--delay-ms-b` | 0 | pause after each call on that side |
| `--timeout` | 60 | seconds per call |
| `--out` | `compare-<timestamp>` | output directory |
| `--no-text` | off | the report shows item ids only, no answer text |
| `--yes` | off | required to make any call |

## Suite format

JSONL, one prompt per line, at most 200 lines (more is refused, not
truncated):

```
{"id": "q017", "user": "Summarise this clause ...", "system": "You are a contracts assistant.", "expect_json": false}
```

`id` and `user` are required. `expect_json: true` turns on the JSON
validity metric for that item.

## How to read the verdicts

A model does not always repeat itself. So for every metric the tool
measures three things: how differently A answers A across repeats, how
differently B answers B, and how differently A and B answer each other.

* **CHANGED** — A vs B differs more than both models differ from
  themselves, and a permutation test (α = 0.01, 999 permutations, seed
  recorded) says the difference is not repetition noise.
* **WITHIN NOISE** — not distinguishable from repetition noise at this
  sample size. This is not "identical" and not "stable".
* **NOT MEASURED** — too few valid answers (fewer than 5 items with two
  valid repeats per side), or a side had more than 10% infrastructure
  failures.

Infrastructure failures (auth, quota, rate limit, provider error,
timeout, network, bad request) are listed separately and never counted
as behaviour. After an auth or quota failure a side stops calling.

If a provider rejects `temperature=0`, that side is retried once without
it and the report header says the side ran at provider default
temperature.

## What it cannot tell you

* Different is not worse. Only JSON validity, truncation and empty
  answers speak to quality; nothing checks correctness.
* The model name returned by the API can be an alias (Mistral returns
  `mistral-small-latest` as given), so it does not prove which concrete
  version answered.
* Refusal detection is a phrase heuristic (`refusal@1`).
* No cost estimate yet.

## Privacy

`evidence.json` contains hashes, lengths, flags, timings and aggregates.
It never contains prompt or answer text. Answer text appears only in the
local `report.html`, and not even there with `--no-text`.

## Provider terms

The tool calls endpoints with your keys on your prompts. Compliance with
each provider's terms is yours.
