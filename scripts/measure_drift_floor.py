"""
scripts/measure_drift_floor.py
==============================
Measure how much an endpoint's behaviour moves (a) when nothing
changed and (b) when the model is swapped.

Standalone measurement instrument. It does NOT import the gateway, does
NOT emit telemetry and does NOT slide the live weather window, so it is
safe to run on demand alongside production. Same posture as
``scripts/measure_google_latency.py``.

It reuses ``probe.canary.execute_canary`` one prompt at a time, so the
hashing and json_valid logic are byte-identical to production. Nothing
is re-implemented here.

Deliberate difference from production: this runner is resilient per
prompt. Production discards a whole suite when any prompt exhausts its
retries (contract CAN-2 s7 R1); an experiment must not lose 49 good
observations to one 429, so a failed prompt is recorded as a row with
ok=false and the run continues. Every rate printed carries its own
denominator.

Usage (PowerShell, from repo root):

  python scripts/measure_drift_floor.py run `
      --model-tuple google/gemini-3.5-flash-lite `
      --base-url https://generativelanguage.googleapis.com/v1beta/openai `
      --label a1 --out docs/evidence/driftfloor

  python scripts/measure_drift_floor.py compare `
      --a docs/evidence/driftfloor/run_a1.csv `
      --b docs/evidence/driftfloor/run_a2.csv

The API key is read from SEISMOGRAPH_PROBE_API_KEY. It is never logged.

#SG-TRACE: REQ-FLOOR-001 | assumption: the same 50-prompt suite run
#   twice against one unchanged model measures the endpoint's own
#   noise floor | test: self-comparison invariant (compare a,a == 1.0)
#SG-TRACE: REQ-FLOOR-002 | assumption: hash agreement and mean output
#   length are the signal; latency is recorded but never a criterion
#   | test: no code path reads latency_ms when deciding anything
#SG-TRACE: REQ-FLOOR-003 | assumption: a prompt that failed in either
#   run is excluded from comparison and counted separately, never
#   scored as "changed" | test: compared_n printed beside every rate
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

# The probe package is imported inside _run() on purpose. The compare
# mode must work on a machine that has only the published CSVs and a
# stdlib Python -- that is what makes these numbers checkable by a
# stranger, which is the whole point of publishing them.
# #SG-TRACE: REQ-FLOOR-004 | assumption: compare is pure arithmetic
#   over two CSVs and needs nothing from this repository
#   | test: compare runs with probe/ absent

# A comparison resting on fewer than this many prompts is not reported
# as a rate. Adversarial case (a): a mostly-failed run must not be able
# to publish a confident-looking agreement number.
MIN_COMPARED = 30

# Categories whose response hash is NOT usable as an identity signal.
#
# MEASURED 2026-09-14: tool_calling answers carry a per-call random id
# inside the tool_calls JSON, and that JSON is what gets hashed. Across
# runs a1/b1, 7 of 8 tool answers had byte-identical OUTPUT LENGTH and
# 0 of 8 matched by hash. A tool canary therefore cannot match itself,
# ever, and any agreement rate that includes it is contaminated.
#
# These prompts are reported separately, on length identity, and are
# excluded from the headline rate. The same contamination exists in
# probe/canary.py, which hashes tool_calls_json the same way -- that is
# a separate open defect, not fixed here.
#
# #SG-TRACE: REQ-FLOOR-005 | assumption: a category whose hash carries
#   a nonce cannot contribute to an identity rate | test: a1 vs b1
#   tool_calling shows 7/8 length-identical and 0/8 hash-identical
VOLATILE_HASH_CATEGORIES = frozenset({"tool_calling"})

FIELDS = [
    "run_id",
    "label",
    "model_tuple",
    "suite_version",
    "prompt_id",
    "category",
    "response_hash",
    "output_length",
    "json_valid",
    "latency_ms",
    "ok",
    "error_class",
]


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _run(args: argparse.Namespace) -> int:
    os.makedirs(args.out, exist_ok=True)
    # MEASURED 2026-09-14: running the same --label twice silently
    # overwrote a clean 50/50 run with a later one, destroying the
    # first run's per-prompt data. A measurement instrument must not
    # be able to delete evidence by accident. Refuse, and say what to
    # do instead.
    # #SG-TRACE: REQ-FLOOR-006 | assumption: an existing CSV for this
    #   label is evidence and is never overwritten without --force
    #   | test: second run with the same label exits 3 and writes
    #   nothing
    csv_path = os.path.join(args.out, f"run_{args.label}.csv")
    if os.path.exists(csv_path) and not args.force:
        print(
            f"REFUSING to run: {csv_path} already exists.\n"
            f"That file is evidence. Use a new --label "
            f"(e.g. {args.label}b), or pass --force to overwrite "
            f"on purpose.",
            file=sys.stderr,
        )
        return 3

    sys.path.insert(
        0,
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    from probe.canary import (
        CANARY_SUITE_V2,
        SUITE_VERSION_V2,
        execute_canary,
    )
    from probe.providers import (
        OpenAICompatibleProvider,
        ProviderError,
    )

    api_key = os.environ.get("SEISMOGRAPH_PROBE_API_KEY") or None
    if api_key is None:
        print(
            "SEISMOGRAPH_PROBE_API_KEY is not set.",
            file=sys.stderr,
        )
        return 2

    provider = OpenAICompatibleProvider(
        base_url=args.base_url,
        api_key=api_key,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )

    run_id = f"{args.label}-{int(time.time())}"
    started = _now()

    rows: list[dict] = []
    n_ok = 0
    n_failed = 0

    total = len(CANARY_SUITE_V2)
    print(
        f"run_id={run_id}  model={args.model_tuple}  "
        f"prompts={total}  max_tokens={args.max_tokens}"
    )

    for idx, prompt in enumerate(CANARY_SUITE_V2, start=1):
        pid = prompt["prompt_id"]
        category = prompt.get("category", "")
        row = {
            "run_id": run_id,
            "label": args.label,
            "model_tuple": args.model_tuple,
            "suite_version": SUITE_VERSION_V2,
            "prompt_id": pid,
            "category": category,
            "response_hash": "",
            "output_length": "",
            "json_valid": "",
            "latency_ms": "",
            "ok": "false",
            "error_class": "",
        }
        try:
            res = execute_canary(
                args.model_tuple,
                suite=[prompt],
                mock=False,
                provider=provider,
                suite_version=SUITE_VERSION_V2,
            )[0]
        except ProviderError as exc:
            row["error_class"] = f"ProviderError:{exc.status_code}"
            n_failed += 1
        except Exception as exc:  # noqa: BLE001
            row["error_class"] = type(exc).__name__
            n_failed += 1
        else:
            row["response_hash"] = res.response_hash
            row["output_length"] = res.output_length
            row["json_valid"] = str(res.json_valid).lower()
            row["latency_ms"] = res.latency_ms
            row["ok"] = "true"
            n_ok += 1

        rows.append(row)
        print(
            f"  [{idx:>2}/{total}] {pid:<26} {row['ok']:<5} "
            f"{row['error_class']}"
        )
        if idx < total:
            time.sleep(args.pacing_ms / 1000.0)

    finished = _now()

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    lengths = [int(r["output_length"]) for r in rows if r["ok"] == "true"]
    structured = [
        r
        for r in rows
        if r["ok"] == "true" and r["category"] == "structured_output"
    ]
    json_ok = [r for r in structured if r["json_valid"] == "true"]

    summary = {
        "run_id": run_id,
        "label": args.label,
        "model_tuple": args.model_tuple,
        "suite_version": SUITE_VERSION_V2,
        "base_url": args.base_url,
        "max_tokens": args.max_tokens,
        "pacing_ms": args.pacing_ms,
        "started_utc": started,
        "finished_utc": finished,
        "n_prompts": total,
        "n_ok": n_ok,
        "n_failed": n_failed,
        "mean_output_length": (
            round(statistics.fmean(lengths), 3) if lengths else None
        ),
        "median_output_length": (
            statistics.median(lengths) if lengths else None
        ),
        "json_valid_numerator": len(json_ok),
        "json_valid_denominator": len(structured),
        "csv": os.path.basename(csv_path),
    }
    json_path = os.path.join(args.out, f"summary_{args.label}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    print("")
    print(f"ok={n_ok}  failed={n_failed}  of {total}")
    print(
        f"mean_output_length={summary['mean_output_length']}  "
        f"median={summary['median_output_length']}"
    )
    print(
        f"json_valid={summary['json_valid_numerator']}"
        f"/{summary['json_valid_denominator']} "
        "(structured_output prompts only)"
    )
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    return 0


def _load(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["prompt_id"]: r for r in csv.DictReader(fh)}


def _compare(args: argparse.Namespace) -> int:
    a = _load(args.a)
    b = _load(args.b)

    shared = sorted(set(a) & set(b))
    ok_both = [
        p for p in shared if a[p]["ok"] == "true" and b[p]["ok"] == "true"
    ]
    failed = len(shared) - len(ok_both)
    volatile = [
        p for p in ok_both if a[p]["category"] in VOLATILE_HASH_CATEGORIES
    ]
    both_ok = [p for p in ok_both if p not in set(volatile)]

    label_a = next(iter(a.values()))["label"] if a else "?"
    label_b = next(iter(b.values()))["label"] if b else "?"
    model_a = next(iter(a.values()))["model_tuple"] if a else "?"
    model_b = next(iter(b.values()))["model_tuple"] if b else "?"

    print(f"A: {label_a}  {model_a}  ({len(a)} rows)")
    print(f"B: {label_b}  {model_b}  ({len(b)} rows)")
    print(
        f"shared prompt_ids: {len(shared)}   ok in both: {len(ok_both)}"
        f"   failed: {failed}"
    )
    print(
        f"hash-comparable: {len(both_ok)}   "
        f"excluded as volatile-hash: {len(volatile)} "
        f"({', '.join(sorted(VOLATILE_HASH_CATEGORIES))})"
    )
    print("")

    if len(both_ok) < MIN_COMPARED:
        print(
            f"REFUSING to report rates: only {len(both_ok)} prompts "
            f"are ok in both runs, floor is {MIN_COMPARED}. "
            "A rate on this base would be a false claim."
        )
        return 1

    identical = [
        p for p in both_ok if a[p]["response_hash"] == b[p]["response_hash"]
    ]
    la = [int(a[p]["output_length"]) for p in both_ok]
    lb = [int(b[p]["output_length"]) for p in both_ok]
    mean_a = statistics.fmean(la)
    mean_b = statistics.fmean(lb)

    print(
        f"identical answers: {len(identical)}/{len(both_ok)} "
        f"= {100 * len(identical) / len(both_ok):.1f}%"
    )
    print(
        f"mean output length: {mean_a:.1f} -> {mean_b:.1f}  "
        f"(delta {mean_b - mean_a:+.1f} chars, "
        f"{100 * (mean_b - mean_a) / mean_a:+.1f}%)"
    )
    print("")

    if volatile:
        same_len = sum(
            1
            for p in volatile
            if a[p]["output_length"] == b[p]["output_length"]
        )
        print(
            f"volatile-hash prompts ({len(volatile)}): hash is a nonce, "
            f"so identity is reported on LENGTH only -- "
            f"{same_len}/{len(volatile)} length-identical"
        )
        print("")

    cats: dict[str, list[str]] = {}
    for p in ok_both:
        cats.setdefault(a[p]["category"] or "(none)", []).append(p)
    print(f"{'category':<22}{'identical':>12}{'of':>6}")
    print("-" * 40)
    for cat in sorted(cats):
        ids = cats[cat]
        same = sum(
            1 for p in ids if a[p]["response_hash"] == b[p]["response_hash"]
        )
        flag = (
            "  <- hash is a nonce, ignore"
            if cat in VOLATILE_HASH_CATEGORIES
            else ""
        )
        print(f"{cat:<22}{same:>12}{len(ids):>6}{flag}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the suite once")
    r.add_argument("--model-tuple", required=True)
    r.add_argument("--base-url", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--out", default="docs/evidence/driftfloor")
    r.add_argument("--max-tokens", type=int, default=128)
    r.add_argument("--pacing-ms", type=int, default=4500)
    r.add_argument("--timeout", type=float, default=90.0)
    r.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing run for this label",
    )
    r.set_defaults(func=_run)

    c = sub.add_parser("compare", help="compare two run CSVs")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.set_defaults(func=_compare)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
