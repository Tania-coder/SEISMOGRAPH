# Google latency, 30 points — 2026-09-10T18:33Z

Raw data: `google-latency-2026-09-10T183302Z.csv` (30 rows, one per
call, every field classifiable by construction).

Run: `scripts/measure_google_latency.py`, n=30, gap 4500 ms (mirrors the
probe's google pacing), client timeout 120 s, model
`gemini-3.5-flash-lite` via the OpenAI-compatible endpoint,
`max_tokens: 8`, prompt "ping". Wall clock 18:33:02Z -> 18:36:48Z.
**`where_measured = local-machine`** on all 30 rows.

## Result

    outcome        success 30 / 30      (no empty_200, no errors)
    http_status    200 x 30
    finish_reason  length x 30          (truncated at max_tokens)
    tokens         4 x 25, 3 x 5        real content, 458-465 bytes
    latency (s)    min 0.59  p50 2.08  p90 6.95  p95 9.60  max 15.09
                   mean 3.17
    over 30 s      0 / 30   95% Wilson interval 0.0000 - 0.1135
    over 90 s      0 / 30

Every call carried a real body ("pong! ..."), so none of these is a fast
empty response masquerading as a success — the distinction the
classifier was written for.

## What this establishes

**At this moment, from this network, the google leg is healthy.** At a
mean of 3.17 s a 50-prompt suite costs 50 x 3.17 + 49 x 4.5 pacing
= 378 s ~= 6.3 min, comfortably inside the 15-minute job ceiling, and
consistent with run #135's observed 4m53s.

The rate of calls exceeding the probe's 30 s timeout is **0/30**, upper
bound 11.4% at 95% confidence. The earlier claim of ~20% is refuted a
second time, now with a sample that can carry a bound.

## What this does NOT establish, stated plainly

1. **It does not explain run #137.** That job burned 15m14s and was
   cancelled at the ceiling on 2026-09-09T19:45Z. At the latency
   measured here a full suite costs ~6 min. Either latency was in a bad
   window at that hour, or the runner's path differs from this one, or
   time went somewhere this measurement does not see. **The cause of
   #137 remains unknown.**

2. **The earlier five-call sample was not wrong, it was a different
   window.** Those calls ran 53.90, 27.34, 16.02, 0.58, 13.19 s, mean
   22.2 s — seven times slower than this batch, hours apart on the same
   day. Both samples are real. The honest reading is that this leg's
   latency is **episodic**, and no single batch characterises it. A
   monitor that reports a mean without a window is repeating the mistake
   this project exists to expose.

3. **It does not measure what the probe actually does.** `max_tokens: 8`
   was chosen to keep the measurement cheap; all 30 rows show
   `finish_reason: length`, i.e. every response was truncated at 8
   tokens. The live canary averages ~131 output tokens
   (`recent_avg_output_length` on the board). Output length drives
   generation latency roughly linearly, so **this measurement
   understates the probe's per-call cost, plausibly by a large factor.**
   That is a flaw in the measurement design, not in the data.

4. **It says nothing about the GitHub runner.** Every row records
   `where_measured = local-machine`. A home ISP path and a runner path
   are different networks and different source addresses.

## Next two measurements, in order

1. **Same script, `--max-tokens 128`**, to match the canary's real
   output profile. Until that exists, no latency number from here may be
   used to reason about suite duration. (The flag does not exist yet;
   adding it is a one-line change to the argument parser.)

2. **The same script from a GitHub runner**, as a standalone workflow
   that uploads the CSV as a build artifact. It does not import the
   probe, does not emit to the gateway, and does not slide the weather
   window, so it is safe to dispatch on demand. This is the only
   measurement that answers the question the three-line frame asks
   first: is this our constant or their API?

Until both exist: do not cut `n`, do not change the atomicity rule, do
not raise the production timeout on the strength of these numbers.

## The one point that stays retired

The 0.58 s call of the earlier sample remains **NOT RECOVERED** (see
`google-call-058s.md`). This batch shows that a sub-second 200 with real
content is the modal behaviour here — 13 of 30 calls came back under
1.0 s — which makes a fast success the likely explanation for it. That
is an inference across samples, not a recovery of the record, so the
entry is unchanged. It no longer matters either way: the rate that
mattered now rests on 30 classifiable points instead of five, one of
which could not be classified at all.
