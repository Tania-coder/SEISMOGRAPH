"""
tests.test_security_logging
===========================
SEC-1: regression + adversarial suite for the log-injection fixes flagged
by CodeQL (py/log-injection) in gateway/auth.py and engine/audit.py.

Coverage
--------
SL1  _sanitize_for_log escapes control chars, truncates AFTER escaping,
     leaves clean hex untouched (unit)
SL2  verify_signature: a public key carrying CR/LF cannot forge a new log
     line (adversarial)
SL3  verify_signature: the exception branch cannot forge a new log line
     via a control-char-laden hex string (adversarial)
SL4  verify_signature return value is unchanged for a normal invalid
     signature (behavioural regression -- fix must not alter True/False)
SL5  AuditReportGenerator.generate coerces alert_id to int and rejects a
     non-int id before any lookup or log call (adversarial taint break)

#SG-TRACE: REQ-AUTH-002 (hardening) + REQ-AUDIT-001 (hardening)
#   | assumption: control-char escaping at the logging boundary is the
#     agreed mitigation; crypto verdicts and report contents are unchanged
#   | test: all SL* tests below
"""

from __future__ import annotations

import logging

import pytest
from engine.audit import AuditReportGenerator
from gateway.auth import _sanitize_for_log, verify_signature

# ---------------------------------------------------------------------------
# SL1 — _sanitize_for_log unit behaviour
# ---------------------------------------------------------------------------


def test_sanitize_escapes_and_truncates_after_escaping() -> None:
    """SL1: control chars are escaped; clean hex is left intact; the length
    bound is measured on the ESCAPED string, never mid-sequence."""
    # Newline and carriage return become visible escapes, not real breaks.
    assert _sanitize_for_log("ab\ncd") == "ab\\x0acd"
    assert _sanitize_for_log("x\r\ny") == "x\\x0d\\x0ay"
    # A DEL (0x7f) and a NUL are escaped too.
    assert _sanitize_for_log("a\x7fb\x00c") == "a\\x7fb\\x00c"
    # Clean hex passes through byte-for-byte (no behavioural change for the
    # normal happy path).
    clean = "deadbeef" * 8
    assert _sanitize_for_log(clean, max_len=999) == clean
    # Truncation happens after escaping and appends an ellipsis; the result
    # never ends in a dangling half-escape.
    out = _sanitize_for_log("\n" * 100, max_len=16)
    assert out.endswith("...")
    assert "\n" not in out
    assert len(out.replace("...", "")) == 16


# ---------------------------------------------------------------------------
# SL2 — adversarial: forged log line via public key (InvalidSignature path)
# ---------------------------------------------------------------------------


def test_verify_log_injection_cannot_forge_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SL2: a key whose hex carries an embedded newline early enough to
    land in the logged slice must not produce a second physical log line.

    bytes.fromhex ignores ASCII whitespace, so "00" + "\\n" + "00"*31 still
    parses to a valid 32-byte key. The signature won't match, so this
    reaches the InvalidSignature branch which logs public_key_hex[:16].
    The newline sits at position 4 -- inside that slice -- so without the
    fix the raw slice would contain a line break."""
    forged = "00" + "\n" + "00" * 31  # 64 hex digits -> 32 bytes, +1 newline
    with caplog.at_level(logging.WARNING, logger="gateway.auth"):
        result = verify_signature(b"payload", "aa" * 64, forged)
    assert result is False
    # Exactly one record; no raw newline; the newline was escaped, proving
    # the sanitizer ran on the slice that used to be logged raw.
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "\n" not in messages[0]
    assert "\\x0a" in messages[0]


# ---------------------------------------------------------------------------
# SL3 — exception branch is sanitized (defense in depth)
# ---------------------------------------------------------------------------


def test_verify_exception_branch_is_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SL3: a non-hex key raises ValueError inside bytes.fromhex and the
    exception text is routed through the sanitizer before logging.

    Note: CPython's fromhex ValueError does not echo the input, so there is
    no *known* natural way to smuggle a control char through this branch
    today -- the sanitizer here is defense in depth. The test still returns
    False, emits exactly one record with no raw newline, and thereby guards
    against a future change that logs a raw exception carrying user data."""
    nasty = "zz-not-hex"
    with caplog.at_level(logging.WARNING, logger="gateway.auth"):
        result = verify_signature(b"payload", "aa" * 64, nasty)
    assert result is False
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "\n" not in messages[0]


# ---------------------------------------------------------------------------
# SL4 — behavioural regression: verdict unchanged for a normal bad signature
# ---------------------------------------------------------------------------


def test_verify_verdict_unchanged_for_clean_invalid_signature() -> None:
    """SL4: a well-formed but wrong signature still returns False, and a
    well-formed missing input still returns False -- the sanitizer must not
    alter the crypto verdict."""
    good_key = "00" * 32  # valid 32-byte hex key, parses fine
    assert verify_signature(b"payload", "bb" * 64, good_key) is False
    assert verify_signature(b"payload", "", good_key) is False
    assert verify_signature(b"payload", "aa" * 64, "") is False


# ---------------------------------------------------------------------------
# SL5 — adversarial: non-int alert_id is rejected before any log call
# ---------------------------------------------------------------------------


def test_generate_rejects_non_int_alert_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SL5: generate() coerces alert_id to int; a control-char-laden string
    raises ValueError before any repository lookup or debug log fires."""

    class _ExplodingRepo:
        def get_local_alert_by_id(self, _id: int) -> None:
            raise AssertionError("lookup must not run for a non-int id")

        def get_public_alert_by_id(self, _id: int) -> None:
            raise AssertionError("lookup must not run for a non-int id")

    gen = AuditReportGenerator(_ExplodingRepo())
    with caplog.at_level(logging.DEBUG, logger="engine.audit"):
        with pytest.raises(ValueError):
            gen.generate("7\nFORGED log line")
    # No audit.generate log records were emitted for the malicious id.
    assert not [
        r for r in caplog.records if "audit.generate" in r.getMessage()
    ]
