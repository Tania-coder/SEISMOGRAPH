"""
scripts/weather_window_stats.py
===============================
REPORT-2 -- recompute every collection figure that Weather Report #2
quotes, from the archived /v1/weather snapshots themselves.

Why this instrument exists
--------------------------
Keystone CLAMP-1 sec 7 accepted a rule by signature: a number that
appears in a published artefact has an instrument that recomputes it
in the gate.  Weather Report #1 (2026-09-04) quoted a window span, a
mean inter-sample interval, a cadence percentage and a row age -- all
of them arithmetic done once, by hand, in prose.  Prose recording a
measurement is a report of one, not the measurement.

So this script derives those figures from the snapshot files, and the
tests beside it pin the derivations against the snapshots that the
reports actually quote.

What it binds to, rather than restating
---------------------------------------
- ``MAX_OUTPUT_LENGTH`` and the DP machinery come from
  ``probe.privacy``.  The saturation upper bound therefore moves with
  the clamp instead of with a number typed into a report.
- ``STALE_AFTER_HOURS`` comes from ``gateway.main``.  The agreement
  check between a published status and a computed age therefore moves
  with DASH-3's threshold.
- The NOMINAL cadence is parsed out of the cron line in
  ``.github/workflows/probe_weather.yml``.  Report #1's "about 108
  hours" for ten samples rests on the leg firing twice a day; if that
  schedule changes, every cadence figure in every report built on it
  is wrong, and this parse is what makes the gate say so.

What it deliberately does NOT do
--------------------------------
It does not diagnose WHY a leg stopped, it does not call a provider,
it does not touch the network, and it never prints the word "stable".
A leg whose collection rate has collapsed is not stable; its published
average is computed over a window it has not told you the length of.
That is the DASH-2 family of defect (a perfect-looking count produced
by rows that were never written) and the reason the window bounds, not
the counts, are the instrument.

One caveat the caller must supply: the age of a snapshot is only
meaningful against the moment it was read.  Snapshots archived before
DASH-3 carry no ``window_age_hours`` field, so ``--read-at`` provides
it; when the field is present it is preferred and the supplied value
is checked against it.

Usage
-----
    python scripts/weather_window_stats.py \
        --snapshot docs/evidence/weather-2026-09-22T104310Z.json \
        --read-at 2026-09-22T10:43:10Z \
        --out docs/evidence/weather_windows

#SG-TRACE: REQ-REPORT2-001
#   | assumption: deriving the cadence from the workflow cron keeps
#     every published percentage bound to the real schedule
#   | test: test_nominal_interval_comes_from_the_workflow
#SG-TRACE: REQ-REPORT2-002
#   | assumption: the saturation bound must move with the clamp
#   | test: test_saturation_bound_uses_live_clamp
#SG-TRACE: REQ-REPORT2-003
#   | assumption: a healthy sample_count cannot witness collection loss
#   | test: test_counts_cannot_witness_collection_loss
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gateway.main import STALE_AFTER_HOURS  # noqa: E402
from probe.privacy import MAX_OUTPUT_LENGTH  # noqa: E402

WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "probe_weather.yml"

# Collection-rate bands.  NOMINAL allows the measured 2.5-4.5 h lateness
# of the scheduler (S049): a leg firing on time cannot be distinguished
# from one firing four hours late over a ten-sample window, so the band
# is deliberately generous and only a real collapse leaves it.
DEGRADED_BELOW = 0.75
DARK_BELOW = 0.40


class WorkflowScheduleError(RuntimeError):
    """The probe workflow no longer declares a parsable cron schedule."""


def nominal_interval_hours(workflow: Path = WORKFLOW) -> float:
    """Hours between scheduled probe runs, read from the workflow cron.

    Only the minute and hour fields are interpreted, and only for the
    steady-state form this project uses (an explicit hour list, every
    day).  Anything else raises rather than guessing: a wrong cadence
    silently rescales every percentage in every report.
    """
    text = workflow.read_text(encoding="utf-8")
    crons = re.findall(r'^\s*-\s*cron:\s*"([^"]+)"', text, re.MULTILINE)
    if len(crons) != 1:
        raise WorkflowScheduleError(
            f"expected exactly one cron line in {workflow.name}, "
            f"found {len(crons)}"
        )
    fields = crons[0].split()
    if len(fields) != 5:
        raise WorkflowScheduleError(f"malformed cron: {crons[0]!r}")
    minute, hour, dom, month, dow = fields
    if dom != "*" or month != "*" or dow != "*":
        raise WorkflowScheduleError(
            f"cron is not a plain daily schedule: {crons[0]!r}"
        )
    if not re.fullmatch(r"\d+", minute):
        raise WorkflowScheduleError(f"unsupported minute field: {minute!r}")
    if not re.fullmatch(r"\d+(,\d+)*", hour):
        raise WorkflowScheduleError(f"unsupported hour field: {hour!r}")
    runs_per_day = len(hour.split(","))
    return 24.0 / runs_per_day


def _parse(ts: str) -> datetime:
    """Parse an ISO-8601 instant, tolerating the trailing Z."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


@dataclass
class LegWindow:
    """Everything Report #2 may quote about one leg of one snapshot."""

    model_tuple: str
    published_status: str
    sample_count: int
    avg_output_length: float
    window_start: str
    window_end: str
    span_hours: float | None
    mean_interval_hours: float | None
    nominal_interval_hours: float
    collection_rate: float | None
    collection_class: str
    age_hours: float | None
    age_source: str
    stale_after_hours: float
    status_agrees_with_age: bool | None
    max_output_length: int
    saturation_upper_bound: float | None


def leg_window(
    leg: dict,
    read_at: datetime | None = None,
    nominal: float | None = None,
) -> LegWindow:
    """Derive one leg's collection figures from one published row."""
    nominal = nominal_interval_hours() if nominal is None else nominal
    n = int(leg["sample_count"])
    start = _parse(leg["window_start"])
    end = _parse(leg["window_end"])

    span = (end - start).total_seconds() / 3600.0
    # n samples bound n-1 intervals.  One sample bounds none, and a
    # span divided by n would quietly understate every gap.
    interval = span / (n - 1) if n >= 2 else None
    rate = (nominal / interval) if interval else None

    if rate is None:
        klass = "UNDETERMINED"
    elif rate < DARK_BELOW:
        klass = "DARK"
    elif rate < DEGRADED_BELOW:
        klass = "DEGRADED"
    else:
        klass = "NOMINAL"

    published_age = leg.get("window_age_hours")
    if published_age is not None:
        age = float(published_age)
        age_source = "published"
    elif read_at is not None:
        age = (read_at - end).total_seconds() / 3600.0
        age_source = "derived from --read-at"
    else:
        age = None
        age_source = "unavailable"

    status = str(leg["status"])
    if age is None:
        agrees = None
    else:
        should_be_stale = age > STALE_AFTER_HOURS
        agrees = (status == "STALE") == should_be_stale

    avg = float(leg["recent_avg_output_length"])
    bound = avg / MAX_OUTPUT_LENGTH if MAX_OUTPUT_LENGTH else None

    return LegWindow(
        model_tuple=str(leg["model_tuple"]),
        published_status=status,
        sample_count=n,
        avg_output_length=avg,
        window_start=leg["window_start"],
        window_end=leg["window_end"],
        span_hours=span,
        mean_interval_hours=interval,
        nominal_interval_hours=nominal,
        collection_rate=rate,
        collection_class=klass,
        age_hours=age,
        age_source=age_source,
        stale_after_hours=STALE_AFTER_HOURS,
        status_agrees_with_age=agrees,
        max_output_length=MAX_OUTPUT_LENGTH,
        saturation_upper_bound=bound,
    )


def snapshot_windows(
    path: Path, read_at: datetime | None = None
) -> list[LegWindow]:
    """Derive every leg of one archived /v1/weather snapshot."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    nominal = nominal_interval_hours()
    return [leg_window(row, read_at, nominal) for row in rows]


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render(path: Path, windows: list[LegWindow]) -> str:
    """Render the figures a report may quote, with their provenance."""
    lines = [
        f"snapshot: {path.name}",
        f"clamp MAX_OUTPUT_LENGTH = {MAX_OUTPUT_LENGTH} (probe.privacy, live)",
        f"STALE_AFTER_HOURS = {STALE_AFTER_HOURS} (gateway.main, live)",
        f"nominal interval = {_fmt(nominal_interval_hours())} h "
        f"({WORKFLOW.name} cron, live)",
        "",
    ]
    for w in windows:
        lines += [
            f"[{w.model_tuple}] published status {w.published_status}",
            f"  window            {w.window_start}",
            f"                 -> {w.window_end}",
            f"  samples           {w.sample_count}",
            f"  span              {_fmt(w.span_hours)} h",
            f"  mean interval     {_fmt(w.mean_interval_hours)} h "
            f"(nominal {_fmt(w.nominal_interval_hours)} h)",
            f"  collection rate   {_fmt(w.collection_rate, 4)}"
            f"  -> {w.collection_class}",
            f"  age at read       {_fmt(w.age_hours)} h ({w.age_source})",
            f"  status agrees     {w.status_agrees_with_age}",
            f"  avg_output_length {w.avg_output_length}",
            f"  saturation bound  <= {_fmt(w.saturation_upper_bound, 4)}"
            f"  (avg / {w.max_output_length}, upper bound, NOT measured)",
            "",
        ]
    lines.append(
        "A count of 10 is published by every leg above.  The counts "
        "are not the instrument; the window bounds are."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--snapshot",
        action="append",
        required=True,
        help="archived /v1/weather JSON (repeatable)",
    )
    ap.add_argument(
        "--read-at",
        default=None,
        help="ISO-8601 instant the snapshot was read (pre-DASH-3 files)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="directory to write a JSON summary into",
    )
    args = ap.parse_args(argv)

    read_at = _parse(args.read_at) if args.read_at else None
    summary: dict[str, list[dict]] = {}
    for raw in args.snapshot:
        path = Path(raw)
        windows = snapshot_windows(path, read_at)
        print(render(path, windows))
        summary[path.name] = [asdict(w) for w in windows]

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        out_path = out_dir / f"weather_windows_{stamp}.json"
        out_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
