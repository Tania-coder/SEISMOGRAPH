"""
tests.test_clamp_saturation
===========================
Gate for the CLAMP-1 instrument (contract accepted S055 with
amendments G-30, G-31, G-32).

What these tests are for
------------------------
The clamp measurement existed as numbers in a session log. A number in
a log is not a gate: nothing fails when the code underneath it moves.
These tests pin the measured values as literals and bind them to the
LIVE constants in probe/privacy.py, so that changing the clamp, the
epsilon or the corpus makes the gate red instead of making a published
report quietly wrong.

The adversarial case is the one that matters: a fully saturated clamp
reports the cap for both legs, the difference collapses to exactly
zero, and with DP noise on top it reads as a small drift rather than
as an absent measurement. The instrument must call that stream
UNINTERPRETABLE and must never call it stable.

#SG-TRACE: REQ-CLAMP-001, REQ-CLAMP-002, REQ-CLAMP-004
#   | assumption: literals plus live-constant binding together make a
#     measurement survivable across sessions
#   | test: (this module)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from probe.privacy import EPSILON, MAX_OUTPUT_LENGTH

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "measure_clamp_saturation.py"
RUN_A = REPO_ROOT / "docs" / "evidence" / "driftfloor" / "run_a1.csv"
RUN_C = REPO_ROOT / "docs" / "evidence" / "driftfloor" / "run_c1.csv"

# Measured 2026-09-19 on the pinned FLOOR-1 CSVs, recomputed by a
# second independent implementation before being written down.
# Changing a value here is never a fix.
PINNED = {
    "mean_a_raw": 166.19047619047618,
    "mean_b_raw": 126.52380952380952,
    "mean_a_clamped": 112.52380952380952,
    "mean_b_clamped": 81.23809523809524,
    "delta_raw": -39.666666666666664,
    "delta_clamped": -31.285714285714278,
    "n_compared": 42.0,
    "saturation_a": 9 / 42,
    "saturation_b": 7 / 42,
}
TOL = 1e-9


def _load():
    """Import the instrument by path; scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location("clampsat", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


m = _load()


def _real():
    import random

    a = m.read_lengths(str(RUN_A))
    b = m.read_lengths(str(RUN_C))
    ids = sorted(set(a) & set(b))
    ra = [float(a[i]) for i in ids]
    rb = [float(b[i]) for i in ids]
    return m.compare(ra, rb, random.Random(42))


def test_instrument_uses_live_constants() -> None:
    """The instrument must not restate 320 or 2.0 as literals.

    If either constant moves, this test fails first and loudly, and
    every pinned number below has to be re-measured rather than
    re-typed.

    #SG-TRACE: REQ-CLAMP-001 | test: (this)
    """
    assert m.MAX_OUTPUT_LENGTH is MAX_OUTPUT_LENGTH
    assert m.EPSILON == EPSILON
    assert MAX_OUTPUT_LENGTH == 320
    assert EPSILON == 2.0
    src = SCRIPT.read_text(encoding="utf-8")
    assert "MAX_OUTPUT_LENGTH = 320" not in src
    assert "EPSILON = 2.0" not in src


def test_real_corpus_numbers_are_pinned() -> None:
    """The positive control still measures what it measured.

    #SG-TRACE: REQ-CLAMP-001 | test: (this)
    """
    r = _real()
    for key, expected in PINNED.items():
        assert abs(r[key] - expected) < TOL, key


def test_both_noise_scales_reported_and_distinct() -> None:
    """A ratio states the n its scale came from.

    The comparison rests on 42 records; the probe flushes 50. Mixing
    them produced a ratio in the S055 chat that was assembled from two
    different n without saying so.

    #SG-TRACE: REQ-CLAMP-004 | test: (this)
    """
    r = _real()
    assert abs(r["noise_scale_flush"] - 320 / 50 / 2.0) < TOL
    assert abs(r["noise_scale_paired"] - 320 / 42 / 2.0) < TOL
    assert r["noise_scale_flush"] != r["noise_scale_paired"]
    assert abs(r["signal_to_noise_flush"] - 9.776785714285714) < 1e-9
    assert r["signal_to_noise_paired"] < r["signal_to_noise_flush"]


def test_positive_control_is_interpretable() -> None:
    """An instrument that can only find breakage is untested.

    The real corpus must come out as a readable signal, or the
    adversarial result below proves nothing.

    #SG-TRACE: REQ-CLAMP-002 | test: (this)
    """
    r = _real()
    assert m.verdict(r["saturation_a"], r["saturation_b"]) == ("INTERPRETABLE")
    assert r["signal_to_noise_flush"] > 3.0


def test_fully_saturated_stream_is_uninterpretable() -> None:
    """ADVERSARIAL: the silent-failure mode, demonstrated.

    A low-spread corpus above the cap saturates both legs. The clamped
    difference is EXACTLY zero while the unclamped difference is large,
    and the verdict must refuse to interpret it.

    #SG-TRACE: REQ-CLAMP-002 | test: (this)
    """
    import random

    sa, sb = m.synthetic(600, 0.10, 0.7613, 42, 42)
    r = m.compare(sa, sb, random.Random(42))
    assert r["saturation_a"] == 1.0
    assert r["saturation_b"] == 1.0
    assert r["delta_clamped"] == 0.0
    assert r["delta_raw"] < -100.0
    assert m.verdict(r["saturation_a"], r["saturation_b"]) == (
        "UNINTERPRETABLE"
    )


def test_noise_makes_a_dead_metric_look_almost_stable() -> None:
    """Why zero is not the number to publish (G-30).

    With DP noise on top, a fully saturated pair does not emit zero --
    it emits a small non-zero difference, which reads as "almost
    stable" rather than as "not measured". That is the dangerous form.

    #SG-TRACE: REQ-CLAMP-002 | test: (this)
    """
    import random

    sa, sb = m.synthetic(600, 0.10, 0.7613, 42, 42)
    r = m.compare(sa, sb, random.Random(7))
    assert r["delta_clamped"] == 0.0
    assert r["delta_clamped_noised"] != 0.0
    assert abs(r["delta_clamped_noised"]) < 4 * r["noise_scale_flush"]


def test_synthetic_is_deterministic() -> None:
    """Same seed, same corpus, or the numbers above mean nothing."""
    first = m.synthetic(600, 0.10, 0.7613, 42, 42)
    second = m.synthetic(600, 0.10, 0.7613, 42, 42)
    assert first == second


def test_reader_is_line_ending_agnostic(tmp_path: Path) -> None:
    """CRLF and LF must parse identically.

    git normalises line endings on commit, so the bytes in the
    repository are not the bytes on the Director's disk. Any check
    that digested these files raw would be platform-dependent.

    #SG-TRACE: REQ-CLAMP-003 | test: (this)
    """
    text = RUN_A.read_text(encoding="utf-8")
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    body = text.replace("\r\n", "\n")
    lf.write_bytes(body.encode())
    crlf.write_bytes(body.replace("\n", "\r\n").encode())
    assert m.read_lengths(str(lf)) == m.read_lengths(str(crlf))


def test_label_guard_refuses_to_overwrite(tmp_path: Path) -> None:
    """Evidence is never overwritten silently.

    FLOOR-1 lost a clean run to a second invocation under the same
    label. The guard exits 3 and writes nothing.
    """
    args = [
        sys.executable,
        str(SCRIPT),
        "--label",
        "guardtest",
        "--out",
        str(tmp_path),
        "--a",
        str(RUN_A),
        "--b",
        str(RUN_C),
    ]
    first = subprocess.run(args, capture_output=True, cwd=REPO_ROOT)
    assert first.returncode == 0
    out = tmp_path / "clamp_guardtest.json"
    before = out.read_text(encoding="utf-8")
    second = subprocess.run(args, capture_output=True, cwd=REPO_ROOT)
    assert second.returncode == 3
    assert b"REFUSING" in second.stderr
    assert out.read_text(encoding="utf-8") == before


def test_written_result_is_readable_and_complete(
    tmp_path: Path,
) -> None:
    """The artefact carries the constants it was measured under."""
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--label",
            "artefact",
            "--out",
            str(tmp_path),
            "--a",
            str(RUN_A),
            "--b",
            str(RUN_C),
        ],
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    )
    data = json.loads(
        (tmp_path / "clamp_artefact.json").read_text(encoding="utf-8")
    )
    assert data["max_output_length"] == MAX_OUTPUT_LENGTH
    assert data["epsilon"] == EPSILON
    assert data["real_verdict"] == "INTERPRETABLE"
    assert len(data["synthetic"]) == 4
    assert any(s["verdict"] == "UNINTERPRETABLE" for s in data["synthetic"])


def test_mean_of_empty_raises() -> None:
    """An empty comparison is an error, never a zero."""
    with pytest.raises(ValueError):
        m.mean([])
