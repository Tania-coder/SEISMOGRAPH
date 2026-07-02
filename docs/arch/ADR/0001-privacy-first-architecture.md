# ADR 0001 — Privacy-first, federated drift detection

- **Status:** Accepted
- **Date:** 2026-06-30
- **Decider:** Tatiana Radchenko (Director)
- **Context:** `SEISMOGRAPH_Architecture.md`, `SECURITY.md`

## Context

SEISMOGRAPH detects semantic drift in third-party LLM APIs by comparing probe
observations across many organisations. The naive design is to collect raw
prompts and model outputs centrally and diff them over time. But the observers
who can provide the most useful signal — companies running real production
traffic — cannot and will not ship raw prompts and outputs off-premises: doing so
leaks proprietary data, user data, and competitive information. A system that
requires raw data gets zero adoption from exactly the observers it needs.

Separately, no single observer can be allowed to trigger a public "this model
drifted" alert. A buggy probe, a transient network issue, or a malicious actor
could otherwise defame a provider or poison the shared signal (a Sybil risk).

## Decision

Adopt a **privacy-first, federated, correlation-gated** architecture:

1. **Raw data never leaves the probe perimeter.** The probe runs inside the
   observer's own infrastructure, executes a fixed, content-addressed canary
   suite at temperature 0, and reduces each response to a SHA-256 hash,
   distributional features, and counts — nothing else.
2. **Differential privacy on outgoing aggregates.** Each transmitted metric is
   perturbed with Laplace noise (ε = 2.0 per flush window) so individual
   responses cannot be reconstructed from the stream.
3. **Signed, schema-locked transport.** Every batch is Ed25519-signed; the
   gateway rejects unsigned or malformed batches and forbids unknown fields.
4. **Correlation-first alerting.** A single-org change-point event is private
   fleet data. Promotion to a public drift alert requires cross-observer quorum
   (≥ 2 independent organisations agreeing).

## Consequences

**Positive**

- Observers can participate without exposing prompts or outputs — the primary
  adoption blocker is removed by construction.
- Public alerts are trustworthy: they require independent agreement, which
  resists both noise and Sybil attacks.
- The privacy boundary is enforced in code (Aggregator metric whitelist, gateway
  schema with `extra=forbid`), not merely documented — it is testable.

**Negative / accepted costs**

- DP noise reduces single-batch metric precision; meaningful signal needs
  aggregation across many batches and observers.
- Quorum means a genuine drift seen by only one observer stays private until a
  second confirms — slightly slower public alerts in a sparse network.
- More moving parts (key management, noise calibration, quorum state) than a
  central plaintext logger.

## Alternatives considered

1. **Central raw-log collection and diff.** Rejected: a non-starter for adoption
   (data leakage) and a single point of privacy failure.
2. **Plaintext telemetry, no DP.** Rejected: distributional features alone can
   still leak; DP makes the privacy claim defensible.
3. **Single-observer alerting.** Rejected: no Sybil resistance; high false-alarm
   and provider-defamation risk.

## References

- `probe/privacy.py` — Aggregator, Laplace DP, metric whitelist
- `probe/crypto.py`, `gateway/auth.py` — Ed25519 sign / verify
- `engine/correlation.py` — AgreementScorer, `QUORUM_MIN = 2`
- `SECURITY.md` — threat model
