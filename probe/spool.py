"""
probe/spool.py
==============
Local on-disk buffer (spool) for signed SignalBatches that could not be
delivered to the ingestion gateway (BUF-1).

Why
---
Before BUF-1 a batch whose POST failed was lost: the canary suite had
already run, the DP noise had already been applied (and, in the SDK,
the epsilon already spent), and the signed bytes were discarded.  The
spool keeps those exact signed bytes and re-sends them on the next run.

What is stored
--------------
Only what would have been transmitted anyway: the canonical JSON body
(DP-noised aggregates, SHA-256 hashes, counts), the Ed25519 signature
and the public key.  No raw prompt, no raw output, no provider API key.
``put`` refuses any body that does not rebuild into a valid
``SignalBatch`` or is not byte-identical to its canonical form, so the
spool cannot become a side channel for anything else.

Re-sending the same noised bytes is post-processing of an already
released DP output, so it costs no additional privacy budget.  The
gateway answers 409 to a batch_id it already holds (REQ-BUF-001), so a
re-send whose first attempt did arrive is never counted twice.

Delivery rules (``drain``)
--------------------------
    202            delivered   -> file removed
    409            duplicate   -> file removed (gateway already has it)
    other 4xx      rejected    -> moved to quarantine/, never retried
    5xx / error    transient   -> kept; draining stops (gateway is down)
    older than max_age_hours   -> removed, logged (default 30 h, equal
                                  to the dashboard's STALE_AFTER_HOURS)
    unreadable / tampered file -> moved to quarantine/

Files are written atomically (temp file + fsync + os.replace), so a
crash mid-write leaves either the old state or the complete new file.

#SG-TRACE: REQ-BUF-002
#   | assumption: the probe host keeps its working directory between
#     runs; an ephemeral CI runner does NOT, so the spool does not help
#     the project's own GitHub Actions leg (documented limitation)
#   | test: test_put_then_drain_delivers_exact_signed_bytes
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from probe.crypto import canonical_json
from probe.privacy import SignalBatch

__all__ = [
    "DEFAULT_MAX_AGE_HOURS",
    "DEFAULT_MAX_FILES",
    "DEFAULT_SPOOL_DIR",
    "DrainReport",
    "Spool",
    "SpoolEntry",
]

logger = logging.getLogger(__name__)

DEFAULT_SPOOL_DIR = ".seismograph_spool"
# Equal to gateway.main.STALE_AFTER_HOURS: a batch older than this would
# be published as stale anyway, and the gateway stamps rows with arrival
# time, so a very late batch would sit at the wrong place on the time
# axis of the detector.
DEFAULT_MAX_AGE_HOURS = 30.0
DEFAULT_MAX_FILES = 100
_FORMAT_VERSION = 1
_QUARANTINE = "quarantine"
_SUFFIX = ".batch.json"
_HEX = frozenset("0123456789abcdef")

# A sender takes (body, headers) and returns the HTTP status code.  Any
# exception it raises is treated as a transient transport failure.
Sender = Callable[[bytes, dict[str, str]], int]


@dataclass(frozen=True)
class SpoolEntry:
    """One spooled, signed batch as read back from disk."""

    path: Path
    batch_id: str
    created_at: float
    body: bytes
    headers: dict[str, str]


@dataclass
class DrainReport:
    """What one ``drain`` call did.  Every file is in exactly one bucket.

    ``remaining`` counts files still waiting after the call; the other
    fields count files this call acted on.
    """

    delivered: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)
    remaining: int = 0
    stopped_on: str | None = None

    def summary(self) -> str:
        """One printable line with every count (denominators visible)."""
        text = (
            f"spool: delivered={len(self.delivered)} "
            f"duplicate={len(self.duplicate)} "
            f"quarantined={len(self.quarantined)} "
            f"expired={len(self.expired)} "
            f"remaining={self.remaining}"
        )
        if self.stopped_on:
            text += f" (stopped: {self.stopped_on})"
        return text


def _validate_body(body: bytes) -> str:
    """Return the batch_id if *body* is a well-formed signed-batch body.

    Raises ValueError otherwise.  The body must rebuild into a
    ``SignalBatch`` (which enforces UUIDs and the metric allow-list and
    rejects unknown top-level fields) and must be byte-identical to its
    own canonical JSON, i.e. exactly what the signature covers.

    #SG-TRACE: REQ-BUF-003
    #   | assumption: SignalBatch(**payload) raises TypeError on any
    #     unexpected top-level key, so a raw-text field cannot slip in
    #   | test: test_put_refuses_body_with_raw_text_field
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"body is not UTF-8 JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError("body is not a JSON object")
    if canonical_json(payload) != body:
        raise ValueError("body is not in canonical JSON form")
    try:
        batch = SignalBatch(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"body is not a valid SignalBatch: {exc}") from None
    hashes = batch.canary_hashes
    if not isinstance(hashes, dict) or not all(
        isinstance(h, str) and len(h) == 64 and set(h) <= _HEX
        for h in hashes.values()
    ):
        raise ValueError("canary_hashes must be 64-char lowercase hex")
    return batch.batch_id


def _check_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return the two signing headers, lower-cased; ValueError if absent."""
    lowered = {k.lower(): v for k, v in headers.items()}
    sig = lowered.get("x-signature", "")
    pub = lowered.get("x-public-key", "")
    if len(sig) != 128 or set(sig) - _HEX:
        raise ValueError("x-signature must be 128 lowercase hex chars")
    if len(pub) != 64 or set(pub) - _HEX:
        raise ValueError("x-public-key must be 64 lowercase hex chars")
    return {"x-signature": sig, "x-public-key": pub}


class Spool:
    """Directory-backed FIFO of signed batches awaiting delivery.

    Parameters
    ----------
    directory:
        Spool root.  Created on first write.  Must not be committed
        (``.seismograph_spool/`` is in .gitignore).
    max_age_hours:
        Entries older than this are dropped on the next ``pending`` /
        ``drain`` call, with a warning.
    max_files:
        Upper bound on waiting entries.  ``put`` evicts the oldest
        entries (with a warning) to stay within it.
    clock:
        Wall-clock source in epoch seconds; injectable for tests.

    #SG-TRACE: REQ-BUF-002
    #   | assumption: single writer per spool directory (one probe
    #     process); concurrent writers are not coordinated
    #   | test: test_drain_order_is_oldest_first
    """

    def __init__(
        self,
        directory: str | Path = DEFAULT_SPOOL_DIR,
        *,
        max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
        max_files: int = DEFAULT_MAX_FILES,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_age_hours <= 0:
            raise ValueError("max_age_hours must be > 0")
        if max_files < 1:
            raise ValueError("max_files must be >= 1")
        self.directory = Path(directory)
        self.max_age_seconds = max_age_hours * 3600.0
        self.max_files = max_files
        self._clock = clock

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def put(self, body: bytes, headers: dict[str, str]) -> Path:
        """Store one signed batch atomically and return its path.

        Raises ValueError (and writes nothing) if the body or the
        signing headers are malformed.

        #SG-TRACE: REQ-BUF-002
        #   | assumption: os.replace is atomic on the same filesystem
        #     (POSIX rename, Windows MoveFileEx with replace)
        #   | test: test_put_leaves_no_temp_file
        """
        batch_id = _validate_body(body)
        sign = _check_headers(headers)
        now = self._clock()
        record = {
            "format": _FORMAT_VERSION,
            "batch_id": batch_id,
            "created_at": now,
            "body_b64": base64.b64encode(body).decode("ascii"),
            "x-signature": sign["x-signature"],
            "x-public-key": sign["x-public-key"],
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        name = f"{int(now * 1000):015d}-{batch_id}{_SUFFIX}"
        final = self.directory / name
        tmp = self.directory / (name + ".tmp")
        data = json.dumps(record, sort_keys=True).encode("utf-8")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, final)
        logger.warning(
            "spool: batch %s stored for later delivery (%s)",
            batch_id,
            final.name,
        )
        self._enforce_cap()
        return final

    def _enforce_cap(self) -> None:
        files = self._files()
        excess = len(files) - self.max_files
        for path in files[: max(excess, 0)]:
            logger.warning(
                "spool: cap %d reached, dropping oldest %s",
                self.max_files,
                path.name,
            )
            path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _files(self) -> list[Path]:
        if not self.directory.is_dir():
            return []
        return sorted(
            p
            for p in self.directory.iterdir()
            if p.is_file() and p.name.endswith(_SUFFIX)
        )

    def _quarantine(self, path: Path, reason: str) -> None:
        qdir = self.directory / _QUARANTINE
        qdir.mkdir(parents=True, exist_ok=True)
        os.replace(path, qdir / path.name)
        logger.error("spool: quarantined %s: %s", path.name, reason)

    def _load(self, path: Path) -> SpoolEntry:
        """Read and re-validate one file; ValueError if it is not sound."""
        try:
            record = json.loads(path.read_bytes().decode("utf-8"))
            if record.get("format") != _FORMAT_VERSION:
                raise ValueError(f"unknown format {record.get('format')!r}")
            body = base64.b64decode(record["body_b64"], validate=True)
            created_at = float(record["created_at"])
            headers = _check_headers(
                {
                    "x-signature": record["x-signature"],
                    "x-public-key": record["x-public-key"],
                }
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            binascii.Error,
        ) as exc:
            raise ValueError(f"unreadable spool file: {exc}") from None
        batch_id = _validate_body(body)
        if batch_id != record.get("batch_id"):
            raise ValueError("batch_id in file does not match body")
        headers["Content-Type"] = "application/json"
        return SpoolEntry(path, batch_id, created_at, body, headers)

    def pending(self) -> list[SpoolEntry]:
        """Return deliverable entries, oldest first.

        Side effects: expired entries are removed and unsound files are
        quarantined, each with a log line.
        """
        return self._scan(DrainReport())

    def _scan(self, report: DrainReport) -> list[SpoolEntry]:
        now = self._clock()
        entries: list[SpoolEntry] = []
        for path in self._files():
            try:
                entry = self._load(path)
            except ValueError as exc:
                self._quarantine(path, str(exc))
                report.quarantined.append(path.name)
                continue
            age = now - entry.created_at
            if age > self.max_age_seconds:
                logger.warning(
                    "spool: batch %s expired after %.1f h, dropped",
                    entry.batch_id,
                    age / 3600.0,
                )
                path.unlink(missing_ok=True)
                report.expired.append(entry.batch_id)
                continue
            entries.append(entry)
        return entries

    # ------------------------------------------------------------------
    # Deliver
    # ------------------------------------------------------------------

    def drain(self, send: Sender) -> DrainReport:
        """Try to deliver every waiting entry, oldest first.

        Stops at the first transient failure (5xx or exception) and
        leaves that entry and all later ones in place.

        #SG-TRACE: REQ-BUF-004
        #   | assumption: 409 means the gateway already holds this exact
        #     batch_id (REQ-BUF-001), so deleting the file loses nothing
        #   | test: test_drain_treats_409_as_delivered
        #SG-TRACE: REQ-BUF-005
        #   | assumption: a 4xx other than 409 is permanent for these
        #     bytes (bad signature, schema); retrying cannot fix it
        #   | test: test_tampered_spool_file_is_quarantined_not_resent
        """
        report = DrainReport()
        entries = self._scan(report)
        for index, entry in enumerate(entries):
            try:
                status = int(send(entry.body, dict(entry.headers)))
            except Exception as exc:  # any transport error is transient
                report.stopped_on = f"{type(exc).__name__}: {exc}"[:200]
                report.remaining = len(entries) - index
                return report
            if status == 202:
                entry.path.unlink(missing_ok=True)
                report.delivered.append(entry.batch_id)
            elif status == 409:
                entry.path.unlink(missing_ok=True)
                report.duplicate.append(entry.batch_id)
            elif 400 <= status < 500:
                self._quarantine(entry.path, f"gateway HTTP {status}")
                report.quarantined.append(entry.batch_id)
            else:
                report.stopped_on = f"gateway HTTP {status}"
                report.remaining = len(entries) - index
                return report
        report.remaining = 0
        return report
