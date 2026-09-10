"""The signing step gets a mechanism instead of another promise.

Protocol 01 requires a Keystone report to be signed BEFORE the task is
merged. It has now been inverted twice: DASH-2 was deployed 2026-09-02
and signed 2026-09-04, and DASH-3 reached `main` before its sec 9 was
signed. The DASH-2 report itself records the rule that a third
occurrence should retire the step rather than ask for more diligence,
because a control that reliably happens after the event it gates is a
ritual.

These tests are that mechanism. They run inside the gate every merge
already executes (`py -3.10 -m pytest -q`), so an unsigned report is now
a red gate rather than an intention. No CI wiring is required, and the
check works locally and offline.

Scope is deliberately narrow: only `docs/keystone/`, which holds the
reports of tasks still being decided. The 25 legacy reports live in
`docs/keystone-archive/` and are deliberately NOT covered.

Measured 2026-09-10: 24 of those 25 carry no signature line at all;
only DASH-2 does. That is not neglect — protocol 01 gained its
signature step at Session 049, long after they were written. Extending
this gate over the archive would therefore either fail permanently or
invite signing them retroactively, which would fabricate a control that
never ran. The archive is history and stays unsigned; the gate applies
to what is still open.

Worth recording next to the gate: across the project's whole history
the signature step has produced exactly two signatures, DASH-2 and
DASH-3, and BOTH were given after their merge rather than before it.
This gate is the first mechanism that can make the order hold, and it
has not yet been tested by a real task -- its first real test is the
next one, not this one.

If this file is ever deleted or its tests skipped instead of satisfied,
the honest response is to strike the signing step from protocol 01 --
not to reinstate the promise.

#SG-TRACE: REQ-PROC-001
"""

from pathlib import Path

_KEYSTONE_DIR = Path(__file__).resolve().parent.parent / "docs" / "keystone"

# Upper case on purpose: prose may discuss an "unsigned" report in lower
# case (this file's own docstring does), and a substring match that
# ignored case would make honest discussion of the control trip it.
_UNSIGNED_MARKER = "UNSIGNED"

# "UNSIGNED" contains "SIGNED", so the positive marker has to be the
# full signature line, not the bare word.
_SIGNED_MARKER = "**SIGNED --"


def _reports() -> list[Path]:
    return sorted(_KEYSTONE_DIR.glob("KEYSTONE_REPORT_*.md"))


def test_keystone_directory_is_where_the_convention_says() -> None:
    """The rule is only enforceable if the directory it names exists."""
    assert _KEYSTONE_DIR.is_dir(), f"missing directory: {_KEYSTONE_DIR}"
    assert _reports(), "no Keystone reports found under docs/keystone/"


def test_no_keystone_report_carries_the_unsigned_marker() -> None:
    """A merged task may not leave its report marked unsigned."""
    offenders = [
        path.name
        for path in _reports()
        if _UNSIGNED_MARKER in path.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "Keystone reports still marked "
        f"{_UNSIGNED_MARKER}: {offenders}. Protocol 01 requires the "
        "signature before the merge; sign the report or, if the step is "
        "being retired, remove it from protocol 01 and delete this test "
        "deliberately."
    )


def test_every_keystone_report_carries_a_signature_line() -> None:
    """Absence of the negative marker is not presence of a signature.

    Deleting the word is not signing. The positive assertion is what
    makes the control hard to satisfy by accident.
    """
    missing = [
        path.name
        for path in _reports()
        if _SIGNED_MARKER not in path.read_text(encoding="utf-8")
    ]
    assert not missing, (
        f"Keystone reports with no {_SIGNED_MARKER!r} line: {missing}"
    )
