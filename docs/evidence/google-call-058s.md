# Archaeology: the 0.58 s google call

One measurement out of a five-call hand-timed sample taken on
2026-09-10 stood at **0.58 s** while the other four stood at 53.90,
27.34, 16.02 and 13.19 s. Before that sample can be used for anything,
this one point has to be classified: a fast SUCCESS belongs in a
latency-of-successes distribution, a fast EMPTY response or a fast
failure does not, and mixing them manufactures a rate that is not real.

## The record

| field | value |
|---|---|
| timestamp | **NOT RECOVERED** — 2026-09-10, exact time never captured |
| latency_s | 0.58 |
| http_status | 200 |
| finish_reason | **NOT RECOVERED** |
| completion_tokens | **NOT RECOVERED** |
| body_bytes | **NOT RECOVERED** |
| body_preview | **NOT RECOVERED** |
| where_measured | Tatiana's machine (home network), NOT a GitHub runner |

## Why it is not recoverable

The sample came from an ad-hoc PowerShell one-liner, not from the probe
and not from a runner, so there is no job log to go back to. The command
was shaped like this:

    1..5 | ForEach-Object {
        $i = $_
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $r = Invoke-WebRequest -Uri $endpoint -Method POST ...
            "call $i HTTP $($r.StatusCode) $($sw.Elapsed.TotalSeconds)s"
        } catch { ... }
    }

Three properties of that shape make the body unrecoverable:

1. Only `$r.StatusCode` and the elapsed time were ever printed. The
   response body was never rendered, never written to disk, never
   hashed.
2. `$r` was reassigned on every iteration, so after the loop it held
   call 5, not call 4. It has since been overwritten again by later
   commands in the same shell.
3. Nothing in the pipeline wrote to a file. There is no raw dump, no
   transcript, and no runner artifact, because the probe was not
   involved at all.

Searching further would be searching for something that was never
written. The honest entry is NOT RECOVERED, and it is entered rather
than reconstructed.

## What IS known, and how far it goes

`http_status = 200` is real, not inferred: PowerShell's
`Invoke-WebRequest` raises on a non-2xx response, so the success branch
that printed the line could only be reached with a 2xx status. The call
therefore was not a client exception and not a 4xx/5xx.

That is the whole of it. Whether the 200 carried a completed generation,
an empty choice, or a zero-token stop is **unknown**, and a 200 alone
does not settle it. Assuming content would be exactly the move this
report exists to prevent.

## Decision

**The 0.58 s point is excluded from every quantitative statement**, and
so, by consequence, is any failure rate or success rate derived from
that five-call sample. It cannot be classified, so it can neither be
counted as a success nor as a failure, and a sample with an
unclassifiable member does not yield a rate at all.

This retires, on the record, the claim made from that sample that ~20%
of calls exceed the 30 s client timeout and that a 50-prompt suite is
therefore ~1-in-70 000 to complete. A complete google suite ran at
2026-09-10T09:49:06Z, which refuted the conclusion independently on the
same day.

What survives the exclusion is only a direction, not a magnitude: **the
latency tail reaches past the probe's own 30 s per-call timeout**, since
a 53.90 s call was observed directly. How often it does so is not known
and is what the 30-point measurement is for.

## What replaces it

`scripts/measure_google_latency.py` records every field in the table
above for every call, so no future point can become unclassifiable. It
has not been run yet. The measurement is a prerequisite for touching the
suite size `n`, the atomicity rule, the production timeout, or CAN-3'.

Note on scope: it measures from a home network, while the probe runs
from a GitHub runner. Those are different network paths and different
source addresses. The result bounds the provider's behaviour as seen
from here; it does not transfer to the runner without saying so.
