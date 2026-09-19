"""
scripts/measure_clamp_saturation.py
===================================
CLAMP-1 -- measure what the output-length clamp does to the drift
signal, instead of predicting it.

Why this instrument exists
--------------------------
Keystone BENCH-1 sec 5.5 predicted that MAX_OUTPUT_LENGTH would
flatten `avg_output_length` on a long-form corpus and destroy the one
feature that separated model generations with no overlap in FLOOR-1.
Session 055 measured it and the prediction was REFUTED: on the FLOOR-1
corpus the clamp removes about a third of the reference leg's mean and
the generation signal survives at roughly ten times the DP noise.

The real failure mode is not mean length but the FRACTION of records
above the cap, which depends on SPREAD.  A heavy-tailed corpus keeps
mass below the cap at any scale; a low-spread corpus saturates
completely, and then both legs report exactly the cap.

That last case is the one worth an instrument.  A fully saturated
clamp emits the cap plus DP noise: a flat line that reads as a
perfectly stable model and is indistinguishable, in every published
field, from real stability.  Ask of any completeness measure what
failure would produce a perfect score; here the answer is saturation.

So this script does not only report numbers -- it CLASSIFIES a stream
as INTERPRETABLE or UNINTERPRETABLE from its saturation fraction, and
refuses to call a saturated stream stable.

Scope (contract CLAMP-1, amendments G-30/G-31/G-32)
---------------------------------------------------
Measurement only.  It imports the live constants from
``probe.privacy`` rather than restating them, so that a change to the
clamp moves this measurement with it and the pinned tests fail loudly.
It reads only committed FLOOR-1 CSVs, writes only under its --out
directory, makes no provider calls and no network calls, and changes
nothing in probe/, engine/ or gateway/.

G-30 is satisfied by printing THREE numbers for every comparison --
before the clamp, after the clamp, and after the clamp with DP noise
applied -- and by naming the operation order explicitly: the probe
clamps each record, then averages, then adds Laplace noise to the
mean (probe/privacy.py, flush()).  Noise is applied AFTER the clamp.

G-31 (the saturation fraction on the LIVE legs) is NOT answered here.
It needs one probe run at the production max_tokens and a working
credential; see the evidence write-up.

Usage
-----
    python scripts/measure_clamp_saturation.py --label c1 \
        --out docs/evidence/clamp

#SG-TRACE: REQ-CLAMP-001
#   | assumption: importing the live constants keeps the measurement
#     bound to the code rather than to a number in a report
#   | test: test_instrument_uses_live_constants
#SG-TRACE: REQ-CLAMP-002
#   | assumption: a saturation fraction at 1.0 makes the metric
#     uninterpretable regardless of how stable it looks
#   | test: test_fully_saturated_stream_is_uninterpretable
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

# The repository root is put on the path before importing probe, the
# same way scripts/measure_drift_floor.py does it, so the instrument
# runs as `python scripts/...` from the repo root without an install.
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

from probe.privacy import (  # noqa: E402
    EPSILON,
    MAX_OUTPUT_LENGTH,
    _laplace_noise,
    _metric_sensitivity,
)

METRIC = "avg_output_length"

# A stream whose records nearly all sit at the cap cannot carry a
# length signal, however stable it looks.  Above this fraction the
# instrument refuses to interpret the metric.
UNINTERPRETABLE_AT = 0.95

# The probe flushes the WHOLE suite, 50 records, and the DP noise it
# adds is scaled to that batch size. A paired comparison excludes the
# tool canaries and rests on fewer records, so the noise implied by the
# comparison is NOT the noise a reader of the board sees.
#
# FOUND BY THIS INSTRUMENT ON ITS FIRST RUN (S056): the session-055
# chat figure |d|/b = 9.78 took the delta from 42 paired records and
# the scale from a 50-record flush. Both numbers were right; putting
# them in one ratio without saying so was not. Both are now printed,
# each labelled with the n it came from, and the headline uses the
# production flush because that is what the published metric carries.
PRODUCTION_FLUSH_N = 50

DEFAULT_A = "docs/evidence/driftfloor/run_a1.csv"
DEFAULT_B = "docs/evidence/driftfloor/run_c1.csv"


def noise_scale(n: int) -> float:
    """Laplace scale the probe would use for a flush of n records.

    Mirrors probe/privacy.py flush(): sensitivity / EPSILON.  Derived
    from the live constants, never restated as a literal.
    """
    return _metric_sensitivity(METRIC, n) / EPSILON


def mean(values: list[float]) -> float:
    """Arithmetic mean.  Raises on an empty sequence, deliberately."""
    if not values:
        raise ValueError("mean of an empty sequence")
    return sum(values) / len(values)


def clamp(values: list[float]) -> list[float]:
    """Apply the probe's per-record clamp to [0, MAX_OUTPUT_LENGTH]."""
    return [float(max(0.0, min(v, MAX_OUTPUT_LENGTH))) for v in values]


def saturation(values: list[float]) -> float:
    """Fraction of records at or above the cap."""
    over = sum(1 for v in values if v >= MAX_OUTPUT_LENGTH)
    return over / len(values)


def read_lengths(path: str) -> dict[str, int]:
    """Read a FLOOR-1 run CSV as TEXT, excluding tool_calling.

    Read as text, never as raw bytes: git normalises line endings on
    commit, so the bytes in the repository differ from the bytes on a
    Windows disk and any byte-level digest of these files would be
    platform-dependent.

    #SG-TRACE: REQ-CLAMP-003
    #   | assumption: CSV line endings are normalised by git, so only
    #     the parsed values are portable
    #   | test: test_reader_is_line_ending_agnostic
    """
    with open(path, encoding="utf-8", newline="") as fh:
        lines = [ln.strip("\r\n") for ln in fh if ln.strip()]
    header = lines[0].split(",")
    i_id = header.index("prompt_id")
    i_cat = header.index("category")
    i_len = header.index("output_length")
    out: dict[str, int] = {}
    for line in lines[1:]:
        field = line.split(",")
        if field[i_cat] == "tool_calling":
            continue
        out[field[i_id]] = int(field[i_len])
    return out


def compare(
    a: list[float],
    b: list[float],
    rng: random.Random,
    flush_n: int = PRODUCTION_FLUSH_N,
) -> dict[str, float]:
    """Three numbers for one comparison, per G-30.

    Before the clamp, after the clamp, and after the clamp with one
    seeded draw of the DP noise the probe would add to each mean.
    The third is what a reader of the board would actually see.

    Two noise scales are reported and never mixed:
      ``noise_scale_paired`` -- implied by the number of records in
        this comparison; internally consistent, but not emitted.
      ``noise_scale_flush``  -- what the probe actually adds for a
        flush of ``flush_n`` records; this is the published one, and
        the one the headline ratio uses.

    #SG-TRACE: REQ-CLAMP-004
    #   | assumption: a ratio must take its delta and its scale from
    #     the same stated n, or state both
    #   | test: test_both_noise_scales_reported_and_distinct
    """
    n = len(a)
    scale_paired = noise_scale(n)
    scale_flush = noise_scale(flush_n)
    ca, cb = clamp(a), clamp(b)
    noised_a = mean(ca) + _laplace_noise(scale_flush, rng)
    noised_b = mean(cb) + _laplace_noise(scale_flush, rng)
    return {
        "n_compared": float(n),
        "n_flush": float(flush_n),
        "noise_scale_paired": scale_paired,
        "noise_scale_flush": scale_flush,
        "mean_a_raw": mean(a),
        "mean_b_raw": mean(b),
        "delta_raw": mean(b) - mean(a),
        "mean_a_clamped": mean(ca),
        "mean_b_clamped": mean(cb),
        "delta_clamped": mean(cb) - mean(ca),
        "delta_clamped_noised": noised_b - noised_a,
        "saturation_a": saturation(a),
        "saturation_b": saturation(b),
        "signal_to_noise_flush": (abs(mean(cb) - mean(ca)) / scale_flush),
        "signal_to_noise_paired": (abs(mean(cb) - mean(ca)) / scale_paired),
    }


def verdict(sat_a: float, sat_b: float) -> str:
    """INTERPRETABLE or UNINTERPRETABLE -- never STABLE.

    A saturated stream is not stable, it is unmeasured.  The
    instrument will not emit a word that a reader could mistake for a
    drift verdict.
    """
    if max(sat_a, sat_b) >= UNINTERPRETABLE_AT:
        return "UNINTERPRETABLE"
    return "INTERPRETABLE"


def synthetic(mean_l: float, cv: float, ratio: float, n: int, seed: int):
    """A low-spread corpus: every answer long and similar.

    Returns (leg_a, leg_b) where leg_b is leg_a scaled by the measured
    generation ratio.  [derived], not measured: the shape is a model
    of a reasoning benchmark, not an observation of one.
    """
    rnd = random.Random(seed)
    base = [max(1.0, rnd.gauss(mean_l, mean_l * cv)) for _ in range(n)]
    return base, [v * ratio for v in base]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", default=DEFAULT_A)
    ap.add_argument("--b", default=DEFAULT_B)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", default="docs/evidence/clamp")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing result for this label",
    )
    args = ap.parse_args()

    # The FLOOR-1 lesson: a second run under the same label silently
    # destroyed a clean measurement.  Check before anything else.
    path = os.path.join(args.out, f"clamp_{args.label}.json")
    if os.path.exists(path) and not args.force:
        print(
            f"REFUSING to run: {path} already exists.\n"
            f"That file is evidence. Use a new --label "
            f"(e.g. {args.label}b), or pass --force.",
            file=sys.stderr,
        )
        return 3
    os.makedirs(args.out, exist_ok=True)

    rng = random.Random(args.seed)
    a_map, b_map = read_lengths(args.a), read_lengths(args.b)
    ids = sorted(set(a_map) & set(b_map))
    ra = [float(a_map[i]) for i in ids]
    rb = [float(b_map[i]) for i in ids]

    print(f"clamp = {MAX_OUTPUT_LENGTH}   epsilon = {EPSILON}")
    print("order of operations: clamp each record -> mean -> Laplace")
    print("noise on the mean (probe/privacy.py flush). Noise AFTER.\n")

    real = compare(ra, rb, rng)
    ratio = real["mean_b_raw"] / real["mean_a_raw"]
    print("POSITIVE CONTROL -- measured FLOOR-1 corpus")
    print(
        f"  compared n          {int(real['n_compared'])}"
        f"   (flush n = {int(real['n_flush'])})"
    )
    print(
        f"  saturation a / b    {real['saturation_a']:.3f} / "
        f"{real['saturation_b']:.3f}"
    )
    print(f"  delta raw           {real['delta_raw']:+9.4f}")
    print(f"  delta clamped       {real['delta_clamped']:+9.4f}")
    print(f"  delta clamped+noise {real['delta_clamped_noised']:+9.4f}")
    print(
        f"  b at flush n        {real['noise_scale_flush']:9.4f}"
        f"   |d|/b = {real['signal_to_noise_flush']:.4f}  <- published"
    )
    print(
        f"  b at compared n     {real['noise_scale_paired']:9.4f}"
        f"   |d|/b = {real['signal_to_noise_paired']:.4f}"
    )
    print(
        f"  verdict             "
        f"{verdict(real['saturation_a'], real['saturation_b'])}\n"
    )

    shapes = []
    print("ADVERSARIAL -- low-spread corpora [derived, not measured]")
    print(
        f"{'mean':>6} {'CV':>5} {'sat':>6} {'d raw':>10} "
        f"{'d clamp':>9} {'d+noise':>9} {'verdict':>16}"
    )
    for mean_l, cv in ((400, 0.10), (600, 0.10), (600, 0.35), (1000, 0.10)):
        sa, sb = synthetic(mean_l, cv, ratio, len(ids), args.seed)
        r = compare(sa, sb, rng)
        r["mean_l"] = float(mean_l)
        r["cv"] = cv
        r["verdict"] = verdict(r["saturation_a"], r["saturation_b"])
        shapes.append(r)
        print(
            f"{mean_l:6d} {cv:5.2f} {r['saturation_a']:6.3f} "
            f"{r['delta_raw']:+10.2f} {r['delta_clamped']:+9.2f} "
            f"{r['delta_clamped_noised']:+9.2f} {r['verdict']:>16}"
        )

    result = {
        "label": args.label,
        "seed": args.seed,
        "max_output_length": MAX_OUTPUT_LENGTH,
        "epsilon": EPSILON,
        "uninterpretable_at": UNINTERPRETABLE_AT,
        "sources": {"a": args.a, "b": args.b},
        "generation_ratio": ratio,
        "real": real,
        "real_verdict": verdict(real["saturation_a"], real["saturation_b"]),
        "synthetic": shapes,
    }
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
