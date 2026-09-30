# D12 -- Failure classification, key expiry, and a private ops channel

Status: PROPOSED, revision 2 (Session 058, 2026-09-30).
Not accepted until the Director signs the contract in section 8.
Review: revision 1 was reviewed by an independent agent against the
code (2 blockers, several majors); all addressed here or listed in
section 9.

## 0. Why

2026-09-19..30 the mistral leg was dark for eleven days. The logs said
only "0/50 prompts completed" [measured, run #179]; the cause -- an
expired API key -- was found in the provider console
[measured, S058]. On 2026-09-10 the same leg failed with HTTP 429
code 1300, an account-level refusal, not a 401 [measured, outage
memo]. The HTTP status of the expiry incident itself was never
recorded, because the probe does not record it.

## 1. What the code does today [measured]

- The transport keeps only the status code. `providers.py:131-132`
  raises `ProviderError(f"provider HTTP {exc.code}")`; the body and
  the provider's error code are discarded.
- The strict runner deliberately drops all error text
  (`canary.py:1702-1703`: "provider exceptions may quote request or
  response fragments"). This contract keeps that decision for
  anything that leaves the machine (section 5).
- Only 429 and 503 are retried (`canary.py:1477`). 500/502/504,
  timeouts and network errors are not (`status_code=None`,
  `providers.py:134-139`, `canary.py:1507-1509`).
- `content: null` and empty `choices` raise `ProviderError` with no
  status (`providers.py:349-351,363-369`). Content-filter and SAFETY
  blocks therefore count today as infrastructure failures.
- After a 401 the runner keeps calling the remaining prompts
  (`canary.py:1678-1723`); on the google leg that is ~220 s of pacing
  [derived].
- `canary.py:1701` catches every exception, including our own bugs.
- A job killed at `timeout-minutes` writes nothing (run #137).

## 2. Rule

- **Infrastructure failure**: no model answer was obtained. Never
  enters drift metrics. Goes to the operations channel.
- **Model outcome**: the provider returned an answer, including a
  filtered, empty, refused or wrong one. Always enters metrics
  (ADR 0002 section 6).

## 3. Classification

Classify on the pair (HTTP status, provider error code/type), through
a per-provider table built ONLY from real captured responses,
committed as test fixtures. A pair not in the table is `unclassified`
and alerts immediately. The table starts from these classes:

| class | typical signals (to be confirmed per provider by fixtures) | action |
|---|---|---|
| `auth` | 401; key invalid/expired codes (Google may return these as 400 `API_KEY_INVALID` [assumed]) | abort run, alert immediately |
| `quota` | 402; 429 with a quota/billing code (OpenAI `insufficient_quota`, Mistral code 1300 [measured 09-10]) | abort run, alert immediately |
| `region_or_permission` | 403 that is not auth (unsupported region, API not enabled, model access) | abort run, alert immediately |
| `model_gone` | 404 model not found / deprecated | abort run, alert immediately |
| `param_rejected` | 400 on `max_tokens`/`temperature` etc. | abort run, alert immediately -- often a provider change |
| `context_length` | 400/413 with a length code | alert; item-level |
| `bad_request` | other 400/422 | alert; our request |
| `rate_limit` | 429 without a quota code | retry; alert when exhausted |
| `provider_transient` | 408, 500, 502, 503, 504, 529 | retry; alert when exhausted |
| `timeout` | client timeout | retry; alert when exhausted |
| `network` | DNS, TLS, reset | retry; alert when exhausted |
| `malformed_response` | 200 with non-JSON body or no `choices` | alert |
| `probe_error` | any exception that is not a `ProviderError` | alert; our bug |
| `deadline` | probe's own deadline reached (section 4) | alert |

Moved OUT of infrastructure into model outcomes: `finish_reason`
content_filter / SAFETY / RECITATION -> outcome `filtered`; 200 with
`content: null` and no filter reason -> outcome `empty`.

Retry set becomes {408, 429-without-quota, 500, 502, 503, 504, 529,
timeout, network}. This changes today's behaviour; the affected
tests (`test_p5_*`, `test_p7_*`) are updated deliberately, not
loosened.

`model_gone` is also a drift event. It is reported on the ops channel
per observer; a public, quorum-gated `MODEL_UNAVAILABLE` status is a
separate decision for the Guide and not part of this contract.

## 4. What changes in a run

- Abort on the first `auth`, `quota`, `region_or_permission`,
  `model_gone` or `param_rejected`: no further calls.
- The metrics rule is unchanged: a run with any infrastructure failure
  emits no metrics (all-or-nothing keeps the DP sensitivity at full n).
  It now emits an ops record instead of nothing.
- `--deadline` stops new calls 60 s before the job ceiling and writes
  the ops record, so a timeout is no longer silent.
- The GitHub job ends with a named annotation per class (e.g.
  "AUTH on mistral: 401 invalid_api_key"), not "exit code 1".

## 5. The ops record and who sees it

Off the machine, per run, only:
`{leg, class, http_status, provider_code (from an allow-listed enum),
count, first_seen, last_seen}`.
No prompt ids, no free text, no request or response fragment.

The provider's error message stays in the LOCAL log only, first 200
characters, with every 8+ character window of any configured key
redacted.

Visibility:
- The ops record goes to the operator who sent it, never to the
  public board. For a company, a public "collection failing: quota"
  line would disclose which provider it uses, that it had a billing
  outage, and when.
- The public board shows only coverage per stream: "observers
  reporting in window: k of M". No class, no org.
- `/v1/ops` accepts only signed records from a registered observer key
  (after G-33 key registration); until then ops records stay in the
  job log and annotation only.
- On a PUBLIC repository, GitHub Actions annotations are public. The
  reference deployment accepts that for its own legs; the
  documentation tells self-hosting operators to decide for theirs.

## 6. Key expiry

- Each leg declares expiry in a NON-secret repository variable, e.g.
  `MISTRAL_KEY_EXPIRES=2027-09-30` or `never`. A date is not a secret.
- A step before the probe:
  - within 7 days -> warning annotation, job continues;
  - on or after the date -> error, job fails with class `auth`;
  - variable missing -> warning "key expiry unknown" on every run.
- Known limit: providers do not expose expiry via the completion API.
  The date is what the operator typed when creating the key. The
  first-401 alert is the backstop.

## 7. Alert delivery

Today, with no new infrastructure: the failed job with its named
annotation; GitHub emails the failure. Known silent-failure modes,
stated: GitHub disables scheduled workflows on public repositories
after 60 days without activity, and failure email goes to the account
that last edited the cron. Next step: the gateway's webhook path for
`/v1/ops`. The channel is the Director's choice.

## 8. Contract (for the Director)

Acceptance:
- Fixtures: at least one real captured 401, 429 and key-invalid body
  per live provider (mistral, google), replayed through the
  classifier, each landing in its class. Providers not yet captured
  are marked, not guessed.
- 401 from a mock -> class `auth` on the first prompt, run aborted,
  zero further provider calls, no metrics row, one ops record,
  annotation names the leg and class.
- 429 with Mistral code 1300 -> `quota`, aborted.
- 429 without a quota code -> retried, then `rate_limit`.
- 502 -> retried, then `provider_transient`.
- 200 + `finish_reason=content_filter` -> no ops record; model outcome
  `filtered`.
- 200 + `content: null` -> model outcome `empty`.
- Unknown (status, code) pair -> `unclassified`, immediate alert.
- A non-provider exception -> `probe_error`.
- Deadline reached -> `deadline` ops record written, non-zero exit.
- The ops record's serialised bytes contain no prompt text, no
  prompt id, and no 8+ character window of any configured key
  (test scans the bytes).
- Expiry variable 5 days ahead -> warning, job succeeds; in the past
  -> error; missing -> "expiry unknown" warning.

Adversarial:
- A provider returns 200 with "Rate limit exceeded" as the completion
  text -> it is a model outcome (`unparseable`/`wrong`). Recorded as a
  known limit: a provider that lies about success cannot be told apart
  here from a model that answers badly.
- A forged ops record for another observer's stream -> rejected
  (signature + registered key), once `/v1/ops` exists.

## 9. Open

- Which channel receives alerts beyond GitHub email (Director).
- Public `MODEL_UNAVAILABLE` status (Guide).
- Registered persistent observer keys (G-33 follow-up); until then
  `/v1/ops` is not exposed.
