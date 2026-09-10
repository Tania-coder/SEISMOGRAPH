"""Measure the google leg's per-call behaviour, one row per call.

NOT RUN YET. This file is the skeleton committed ahead of the
measurement so that the fields are agreed before any number exists --
the five-call sample of 2026-09-10 produced a point that could not be
classified afterwards (see docs/evidence/google-call-058s.md), and the
fix for that is to decide what to record BEFORE recording it.

Every call writes a fully classifiable row: a fast 200 with content and
a fast 200 with an empty choice are different events and must never
collapse into the same "success".

Usage (from the repository root, deliberately explicit):

    py -3.10 scripts/measure_google_latency.py --n 30 --gap-ms 4500

Reads the key from business/google_key.txt (gitignored). Writes
docs/evidence/google-latency-<UTC timestamp>.csv and prints a summary.

Scope, stated in the output and in the CSV itself: this runs from
whatever machine invokes it. The probe runs from a GitHub runner. Those
are different network paths and different source addresses, so a result
here bounds what the provider does as seen from HERE and does not
transfer to the runner without saying so.

Privacy note: `body_preview` is bounded to 80 characters of the model's
reply to a fixed, non-sensitive prompt ("ping") that this script itself
sends. It is a deliberate, bounded exception for a diagnostic artefact,
not a precedent -- the probe's own privacy perimeter is unchanged and
raw model output still never leaves it.

#SG-TRACE: REQ-OBS-002
#   | assumption: a latency sample is only interpretable if every point
#     carries the fields needed to classify it as success, empty or
#     failure; a bare (latency, status) pair is not enough, as the
#     0.58 s point proved
#   | test: (measurement script; no unit test -- it makes live calls)
"""

from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_PATH = ROOT / "business" / "google_key.txt"
EVIDENCE_DIR = ROOT / "docs" / "evidence"

ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)
MODEL = "gemini-3.5-flash-lite"
PROMPT = "ping"
MAX_TOKENS = 8

FIELDS = [
    "ts_utc",
    "call_index",
    "latency_s",
    "http_status",
    "finish_reason",
    "completion_tokens",
    "prompt_tokens",
    "body_bytes",
    "body_preview",
    "error_class",
    "outcome",
    "where_measured",
    "gap_ms",
    "timeout_s",
    "model",
    "endpoint",
]


def _read_key() -> str:
    if not KEY_PATH.is_file():
        sys.exit(
            f"missing {KEY_PATH}. Put the Gemini API key there "
            "(business/ is gitignored) and re-run."
        )
    key = KEY_PATH.read_text(encoding="utf-8").strip()
    if not key:
        sys.exit(f"{KEY_PATH} is empty.")
    return key


def _classify(
    status: int | None,
    completion_tokens: int | None,
    body_bytes: int | None,
    error_class: str | None,
) -> str:
    """success | empty_200 | http_error | transport_error | unclassified.

    A 200 is not a success on its own. That distinction is the entire
    reason this script exists.
    """
    if error_class:
        return "transport_error"
    if status is None:
        return "unclassified"
    if status >= 400:
        return "http_error"
    if completion_tokens is None or body_bytes is None:
        return "unclassified"
    if completion_tokens <= 0:
        return "empty_200"
    return "success"


def _one_call(key: str, timeout_s: float) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": PROMPT}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )

    status: int | None = None
    finish_reason = ""
    completion_tokens: int | None = None
    prompt_tokens: int | None = None
    body_bytes: int | None = None
    preview = ""
    error_class = ""

    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
            status = resp.status
            body_bytes = len(raw)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                choices = payload.get("choices") or []
                if choices:
                    finish_reason = str(choices[0].get("finish_reason") or "")
                    message = choices[0].get("message") or {}
                    preview = str(message.get("content") or "")[:80]
                usage = payload.get("usage") or {}
                completion_tokens = usage.get("completion_tokens")
                prompt_tokens = usage.get("prompt_tokens")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
        body_bytes = len(raw)
        preview = raw.decode("utf-8", "replace")[:80]
        error_class = ""
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as exc:
        error_class = type(exc).__name__
    elapsed = time.monotonic() - started

    return {
        "latency_s": round(elapsed, 3),
        "http_status": status if status is not None else "",
        "finish_reason": finish_reason,
        "completion_tokens": (
            completion_tokens if completion_tokens is not None else ""
        ),
        "prompt_tokens": prompt_tokens if prompt_tokens is not None else "",
        "body_bytes": body_bytes if body_bytes is not None else "",
        "body_preview": preview.replace("\n", " ").replace("\r", " "),
        "error_class": error_class,
        "outcome": _classify(
            status, completion_tokens, body_bytes, error_class or None
        ),
    }


def _wilson(successes: int, total: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Printed instead of a bare percentage on purpose: at n=5 the interval
    on 1/5 spans most of the unit line, and quoting the point estimate
    without it is what produced the retracted "~20% of calls" claim.
    """
    if total == 0:
        return (0.0, 1.0)
    z = 1.96
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    half = (
        z
        * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5)
        / denom
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=4500,
        help="pause between calls; 4500 mirrors the probe's google leg",
    )
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument(
        "--where",
        default="local-machine",
        help="recorded in every row; use 'github-runner' when applicable",
    )
    args = parser.parse_args()

    key = _read_key()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_path = EVIDENCE_DIR / f"google-latency-{stamp}.csv"

    rows: list[dict] = []
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(1, args.n + 1):
            if index > 1 and args.gap_ms > 0:
                time.sleep(args.gap_ms / 1000.0)
            row = _one_call(key, args.timeout_s)
            row.update(
                {
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                    "call_index": index,
                    "where_measured": args.where,
                    "gap_ms": args.gap_ms,
                    "timeout_s": args.timeout_s,
                    "model": MODEL,
                    "endpoint": ENDPOINT,
                }
            )
            writer.writerow(row)
            handle.flush()
            rows.append(row)
            print(
                f"{index:3d}/{args.n}  {row['latency_s']:7.2f}s  "
                f"status={row['http_status']}  {row['outcome']}"
            )

    total = len(rows)
    successes = sum(1 for r in rows if r["outcome"] == "success")
    over_30 = sum(
        1
        for r in rows
        if r["outcome"] == "success" and float(r["latency_s"]) > 30.0
    )
    lo, hi = _wilson(over_30, successes)
    lat = sorted(
        float(r["latency_s"]) for r in rows if r["outcome"] == "success"
    )

    print(f"\nwrote {out_path}")
    print(f"calls={total} success={successes}")
    for name in ("empty_200", "http_error", "transport_error", "unclassified"):
        count = sum(1 for r in rows if r["outcome"] == name)
        if count:
            print(f"  {name}={count}")
    if lat:
        mid = lat[len(lat) // 2]
        print(f"success latency: min={lat[0]:.2f}s median={mid:.2f}s max={lat[-1]:.2f}s")
    print(
        f"successes over the probe's 30s timeout: {over_30}/{successes} "
        f"(95% Wilson interval {lo:.2f}-{hi:.2f})"
    )
    print(
        "Interval, not point estimate. Measured from "
        f"{args.where!r}; the probe runs from a GitHub runner and this "
        "does not transfer without saying so."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
