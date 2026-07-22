"""
seismograph.engine.correlation
================================
Change-point detection stubs and cross-observer agreement scoring for
semantic drift signals.

This module has two distinct roles:

1. **Interface stubs** -- CUSUMDetector is preserved here as a typed
   interface contract.  The LIVE Page-CUSUM implementation is in
   engine/detector.py.  Do NOT import CUSUMDetector from this module
   for production use.

2. **AgreementScorer (LIVE)** -- Cross-observer quorum gate (FIX-2).  A
   single-org signal is NEVER promoted to a public drift alert.  Agreement
   is scoped per (model_tuple, metric_name); each candidate expires after a
   candidate TTL; and the required quorum scales with the live observer
   population M as q(M) = max(QUORUM_FLOOR, ceil(M/3)) before
   promote_to_public_alert() returns a non-None count (FIX-2b Seismo bound).

3. **BayesianOnlineDetector (IMPLEMENTED, not wired)** -- Adams & MacKay 2007
   BOCD with Normal-Inverse-Gamma conjugate prior.  Implemented here but NOT
   on the live promotion path: the gateway public path wires the Page-CUSUM
   detector (engine/detector.py, imported in gateway/main.py), so the LIVE
   candidate generator is CUSUM.  The FIX-2b p-anchor (CUSUM ARL0) therefore
   matches the wired detector; if BOCD (hazard 1/200) is later wired in, p
   must be re-anchored to it before trusting the quorum schedule.

All threshold decisions must be documented as labelled data in
data/drift_labels/ before any production deployment.

#SG-TRACE: REQ-ENGINE-002
#   | assumption: feature vectors arrive as float arrays with fixed
#     dimensionality per model tuple
#   | test: test_correlation_vector_shape
#SG-TRACE: REQ-ENGINE-003
#   | assumption: cross-observer quorum >= 2 orgs sufficient for Phase 0
#   | test: test_agreement_scorer_quorum
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Quorum-scaling policy (FIX-2)
# ---------------------------------------------------------------------------
# The public-alert quorum scales with the live observer population M for a
# (model_tuple, metric_name) stream so that a fixed absolute threshold cannot
# be trivially met as the network grows.
#
#     q(M) = max(QUORUM_FLOOR, ceil(QUORUM_FRAC_NUM * M / QUORUM_FRAC_DEN))
#            = max(3, ceil(M/3))   with the FIX-2b defaults
#
# FIX-2b calibration (the "Seismo bound", S039) replaced the FIX-2 synthetic
# frac=1/2 (ceil(M/2)) with an analytically-derived schedule.  Method: model
# the public false-positive per candidate-TTL window as X ~ Binomial(M, p),
# p = per-org stable-window false-candidate rate, and detection power as
# Y ~ Binomial(M, d).  The binding constraint turned out to be POWER (false
# negatives), not FP: at p anchored to the CUSUM ARL0~=500 (p~=0.028 at
# cadence 1/day, TTL 14d) the shipped ceil(M/2) suppressed FP by 5-10 orders
# of magnitude (1e-6..1e-12) while eroding power (a genuine drift seen by 70%
# of orgs promoted with prob 0.34 at M=3, and ceil(M/2) demanded a MAJORITY
# agree -- unreachable when only a minority of canaries cover the fault).
#
# The FIX-2b schedule ceil(M/3): (a) equals the floor of 3 across the near-
# term horizon M<=9 (where the network actually lives -- identical to both the
# honest-noise optimum and to the old policy there, so no regression);
# (b) rises gently past M=10 as an honest hedge against the estimation x
# correlation worst case an adversarial review flagged -- baseline estimation
# (30 samples) can inflate the median per-stream p to ~0.074, at which a
# common-mode correlation rho~=0.08 pushes FP(M=10, q=3) past 0.05; ceil(M/3)
# keeps the worst-case beta-binomial FP <= 0.05 at M=10/15/20 (0.036/0.046/
# 0.032) while staying within the detection-power ceiling.
#
# floor=3 is retained for an ADVERSARIAL (Sybil) reason, NOT a statistical
# one: the FP model does not require it (q=2 already holds FP), but a floor of
# 3 means one Sybil identity plus a single honest false alarm cannot reach
# quorum.  The proportional term gives NO additional headroom against a
# colluding/correlated adversary as M grows -- that is the job of reputation
# weighting + Ed25519 one-org-one-key binding (Phase 2), not this layer.
#
# candidate TTL: each org's candidate alert (and each observer heartbeat)
# counts toward its (model_tuple, metric_name) stream only while it is newer
# than DEFAULT_TTL_NS.  FIX-2b validated the 14-day window analytically: at
# cadence ~1/day it sits inside the feasible band [~5 d cross-org detection
# spread, ~25.6 d FP ceiling]; sampling faster than ~1.5/day/metric pushes 14
# d out of band -> shorten TTL or raise the floor.
#
# #SG-TRACE: REQ-ENGINE-012
# #   | assumption: q(M) = max(3, ceil(M/3)) is the FIX-2b Seismo-bound
# #     schedule; floor=3 is Sybil-justified; p anchored to CUSUM ARL0 (the
# #     LIVE detector), pending real-traffic recalibration of p and rho
# #   | test: test_required_quorum_scaling
# #SG-TRACE: REQ-ENGINE-013
# #   | assumption: candidate/observer TTL is event-time (wall-clock ns);
# #     Redis backend rescales to ms to stay within IEEE-754 ZSET score
# #     precision (ns would exceed 2**53)
# #   | test: test_agreement_scorer_ttl_expiry

QUORUM_FLOOR: int = 3
"""Minimum distinct agreeing orgs for a public alert, regardless of M."""

QUORUM_FRAC_NUM: int = 1
QUORUM_FRAC_DEN: int = 3
"""Proportional term: quorum grows as ceil(NUM * M / DEN) of the population.

FIX-2b (Seismo bound): frac_den raised 2 -> 3.  The gentle ceil(M/3) slope
keeps q(M)=floor across the near-term horizon (q=3 for M<=9), then rises one
step per ~3 orgs.  See the policy note above and
data/drift_labels/quorum_seismo_bound.md for the derivation."""

DEFAULT_TTL_NS: int = 14 * 86_400 * 1_000_000_000
"""Candidate / observer expiry window: 14 days in nanoseconds."""


def required_quorum(
    network_size: int,
    floor: int = QUORUM_FLOOR,
    frac_num: int = QUORUM_FRAC_NUM,
    frac_den: int = QUORUM_FRAC_DEN,
) -> int:
    """Return the quorum threshold q(M) for a live observer population M.

    q(M) = max(floor, ceil(frac_num * M / frac_den)).

    Args:
        network_size: Distinct orgs observing this stream within the TTL
            window (M).  Negative values are treated as 0.
        floor: Absolute minimum quorum (default QUORUM_FLOOR = 3).
        frac_num: Numerator of the proportional term (default 1).
        frac_den: Denominator of the proportional term (default 2).

    Returns:
        The minimum number of distinct agreeing orgs required to promote a
        public alert for a population of ``network_size`` observers.

    #SG-TRACE: REQ-ENGINE-012
    #   | assumption: ceil division via integer arithmetic; frac_den > 0
    #   | test: test_required_quorum_scaling
    """
    m = max(0, network_size)
    scaled = (frac_num * m + frac_den - 1) // frac_den  # ceil(frac_num*m/den)
    return max(floor, scaled)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class FeatureVector:
    """A privacy-preserving feature vector emitted by a probe.

    Contains distributional statistics and/or DP-noised aggregates only.
    Raw prompt text and raw model output are NEVER present here.

    Attributes:
        org_id: Pseudonymous probe identifier bound to an Ed25519 public key.
        model_tuple: Composite model identifier, e.g. "openai/gpt-4o@2025-08".
        suite_version_hash: SHA-256 hash of the canary suite definition.
        values: Ordered list of feature metric values (DP-noised floats).
        timestamp_ns: Probe wall-clock time in monotonic nanoseconds.

    #SG-TRACE: REQ-ENGINE-004
    #   | assumption: org_id is pseudonymous; actual org identity held
    #     only by ingestion gateway key registry
    #   | test: test_feature_vector_no_raw_content
    """

    org_id: str
    model_tuple: str
    suite_version_hash: str
    values: list[float]
    timestamp_ns: int


@dataclass
class ChangePointResult:
    """Result of a change-point detection run for one model tuple.

    Attributes:
        model_tuple: Composite model identifier this result relates to.
        change_detected: True if the detector crossed its alert threshold.
        score: The detector statistic at evaluation time.
        threshold: The detection threshold in effect.
        contributing_orgs: Pseudonymous org_ids behind this signal.
        metric_name: Which metric drifted (e.g. "json_success_rate").  The
            quorum gate matches agreement per (model_tuple, metric_name):
            two orgs drifting on DIFFERENT metrics do NOT agree.  Empty
            string means "unspecified" (legacy callers; treated as a single
            catch-all metric bucket).
        timestamp_ns: Event-time of the candidate in wall-clock nanoseconds.
            Used by AgreementScorer for candidate TTL expiry.  0 means unset;
            the scorer then stamps arrival time on ingest.

    #SG-TRACE: REQ-ENGINE-005
    #   | assumption: change_detected is conservative (false-negative
    #     preferred over false-positive at Phase 0 calibration)
    #   | test: test_cusum_no_false_positive_stable_window
    #SG-TRACE: REQ-ENGINE-012
    #   | assumption: metric_name is carried so cross-observer agreement is
    #     per (model_tuple, metric_name), not per model_tuple alone
    #   | test: test_agreement_scorer_metric_scoped
    """

    model_tuple: str
    change_detected: bool
    score: float
    threshold: float
    contributing_orgs: list[str] = field(default_factory=list)
    metric_name: str = ""
    timestamp_ns: int = 0


# ---------------------------------------------------------------------------
# CUSUMDetector -- INTERFACE STUB ONLY
# ---------------------------------------------------------------------------


class CUSUMDetector:
    """Cumulative-sum change-point detector -- INTERFACE STUB.

    WARNING: raises NotImplementedError on every call.
    The LIVE Page-CUSUM implementation is in engine/detector.py.

    #SG-TRACE: REQ-ENGINE-006
    #   | assumption: CUSUM threshold calibrated offline on labelled data
    #   | test: test_cusum_threshold_calibration
    """

    def __init__(
        self,
        threshold: float = 5.0,
        drift_delta: float = 0.5,
    ) -> None:
        self.threshold: float = threshold
        self.drift_delta: float = drift_delta
        self._cusum_pos: float = 0.0
        self._cusum_neg: float = 0.0

    def update(self, value: float) -> bool:
        """Raises NotImplementedError. Use engine.detector.CUSUMDetector."""
        raise NotImplementedError(
            "CUSUMDetector.update -- stub only. "
            "Use engine.detector.CUSUMDetector for production code."
        )

    def reset(self) -> None:
        """Reset S+ and S- accumulators to zero."""
        self._cusum_pos = 0.0
        self._cusum_neg = 0.0


# ---------------------------------------------------------------------------
# BayesianOnlineDetector -- LIVE (Adams & MacKay 2007)
# ---------------------------------------------------------------------------


class BayesianOnlineDetector:
    """Bayesian online change-point detection (Adams & MacKay 2007).

    Maintains a posterior distribution over run lengths r_t (time steps
    since the last change point) using a Normal-Inverse-Gamma (NIG)
    conjugate prior and a constant hazard rate h.

    **Key design invariant (correctness):**
    The changepoint mass uses the *prior* predictive P(x_t | NIG prior),
    while the growth mass uses each run's accumulated posterior predictive.
    This ensures that an observation far from the learned run distribution
    but plausible under the prior raises P(r_t=0) toward 1.0.

    Concretely, the update recursion is:

        P(r_t=0 | x_{1:t}) proportional to
            h * P(x_t | mu0, kappa0, alpha0, beta0)   [fresh prior]

        P(r_t=r+1 | x_{1:t}) proportional to
            P(r_{t-1}=r | x_{1:t-1}) * (1-h)
                * P(x_t | NIG posterior after r obs)

    The predictive P(x_t | NIG params) is Student-t with:
        nu      = 2 * alpha
        loc     = mu
        scale^2 = beta * (kappa+1) / (alpha * kappa)

    Numerical stability: arithmetic uses direct probability space with
    renormalisation at each step; hypotheses below _PRUNE_THRESHOLD are
    discarded to cap memory at O(T/pruning_rate).

    Reference:
        Adams, R. P., & MacKay, D. J. C. (2007). Bayesian Online
        Changepoint Detection. arXiv:0710.3742.

    Default prior (alpha0=2.0, beta0=0.01):
        E[sigma^2] = beta0/(alpha0-1) = 0.01 -> prior std ~ 0.1.
        Suitable for normalised metrics (json_success_rate, etc.).
        Tune beta0 upward for metrics with higher expected variance.

    #SG-TRACE: REQ-ENGINE-007
    #   | assumption: hazard rate is constant; prior is Normal-Inverse-Gamma
    #   | test: test_bayesian_online_detects_mean_shift
    """

    _PRUNE_THRESHOLD: float = 1e-10
    """Hypotheses with posterior probability below this value are discarded."""

    def __init__(
        self,
        hazard_rate: float = 1.0 / 200.0,
        mu0: float = 0.0,
        kappa0: float = 1.0,
        alpha0: float = 2.0,
        beta0: float = 0.01,
        alert_threshold: float = 0.5,
    ) -> None:
        """Initialise the Bayesian online detector.

        Args:
            hazard_rate: Prior probability that any given time step is a
                change point.  Default 1/200 (one change per 200 obs).
            mu0: NIG prior mean.  Set to the expected baseline metric value.
            kappa0: NIG prior pseudo-count for the mean (> 0).
            alpha0: NIG prior shape parameter (> 0).  Default 2.0 gives a
                proper prior with finite E[sigma^2].
            beta0: NIG prior scale parameter (> 0).  Controls expected
                process variance: E[sigma^2] = beta0/(alpha0-1).
                Default 0.01 -> prior std ~ 0.1, suitable for rates in [0,1].
            alert_threshold: Posterior P(changepoint) at or above which a
                change is considered detected.  Stored for caller inspection;
                update() always returns the raw probability.

        Raises:
            ValueError: If alpha0, beta0, or kappa0 are not positive, or
                if hazard_rate is not in the open interval (0, 1).
        """
        if alpha0 <= 0.0 or beta0 <= 0.0 or kappa0 <= 0.0:
            raise ValueError("alpha0, beta0, kappa0 must be > 0")
        if not (0.0 < hazard_rate < 1.0):
            raise ValueError("hazard_rate must be in (0, 1)")

        self.hazard_rate: float = hazard_rate
        self.alert_threshold: float = alert_threshold

        # NIG prior hyperparameters -- fixed, used to seed each new segment.
        self._mu0: float = mu0
        self._kappa0: float = kappa0
        self._alpha0: float = alpha0
        self._beta0: float = beta0

        # Prior predictive scale^2 (precomputed, constant across all steps).
        self._prior_nu: float = 2.0 * alpha0
        self._prior_scale_sq: float = (
            beta0 * (kappa0 + 1.0) / (alpha0 * kappa0)
        )

        # Parallel arrays: index k = run-length hypothesis r_t=k.
        # NIG sufficient statistics accumulated over the run of length k.
        # Initialised with a single hypothesis r_0=0 and prior params.
        self._run_probs: list[float] = [1.0]
        self._mu: list[float] = [mu0]
        self._kappa: list[float] = [kappa0]
        self._alpha: list[float] = [alpha0]
        self._beta: list[float] = [beta0]

    @staticmethod
    def _student_t_logpdf(
        x: float,
        nu: float,
        loc: float,
        scale_sq: float,
    ) -> float:
        """Log-PDF of Student-t(nu, loc, scale_sq) at x.

        Args:
            x: Observation value.
            nu: Degrees of freedom (> 0).
            loc: Location parameter.
            scale_sq: Squared scale parameter (> 0).

        Returns:
            Log probability density (float).
        """
        z = (x - loc) ** 2 / scale_sq
        return (
            math.lgamma((nu + 1.0) / 2.0)
            - math.lgamma(nu / 2.0)
            - 0.5 * math.log(math.pi * nu * scale_sq)
            - (nu + 1.0) / 2.0 * math.log(1.0 + z / nu)
        )

    def _run_predictive(self, x: float, idx: int) -> float:
        """P(x | NIG posterior for run hypothesis at index idx).

        Returns probability (not log), clamped at exp(-700) for stability.
        """
        kappa = self._kappa[idx]
        alpha = self._alpha[idx]
        nu = 2.0 * alpha
        scale_sq = self._beta[idx] * (kappa + 1.0) / (alpha * kappa)
        lp = self._student_t_logpdf(x, nu, self._mu[idx], scale_sq)
        return math.exp(max(lp, -700.0))

    @staticmethod
    def _nig_update(
        x: float,
        mu: float,
        kappa: float,
        alpha: float,
        beta: float,
    ) -> tuple[float, float, float, float]:
        """Closed-form NIG posterior after observing x.

        Args:
            x: New scalar observation.
            mu, kappa, alpha, beta: Current NIG hyperparameters.

        Returns:
            Tuple (mu_new, kappa_new, alpha_new, beta_new).
        """
        kappa_new = kappa + 1.0
        mu_new = (kappa * mu + x) / kappa_new
        alpha_new = alpha + 0.5
        beta_new = beta + kappa * (x - mu) ** 2 / (2.0 * kappa_new)
        return mu_new, kappa_new, alpha_new, beta_new

    def update(self, value: float) -> float:
        """Return posterior probability of a change point at this step.

        Executes one step of the BOCD recursion:
          1. Changepoint mass = h * P(x_t | PRIOR) -- fresh-start predictive.
          2. Growth mass[r] = P(r_{t-1}=r) * (1-h) * P(x_t | run[r] stats).
          3. Normalise; prune hypotheses below _PRUNE_THRESHOLD.
          4. Update NIG sufficient statistics for all surviving hypotheses.

        Using the prior predictive for the changepoint hypothesis (not the
        run-length predictive) is the key correctness invariant: when x_t is
        very unlikely under the learned tight distribution but plausible under
        the wider prior, P(r_t=0) rises toward 1.0.

        Args:
            value: The next scalar observation in the metric stream.

        Returns:
            Posterior probability in [0.0, 1.0] that a change point
            occurred at this time step.  Values above alert_threshold
            indicate a detected regime shift.

        #SG-TRACE: REQ-ENGINE-007
        #   | test: test_bayesian_online_detects_mean_shift
        """
        x = value
        h = self.hazard_rate
        n = len(self._run_probs)

        # --- 1. Changepoint mass: h * P(x | PRIOR) ---
        prior_lp = self._student_t_logpdf(
            x, self._prior_nu, self._mu0, self._prior_scale_sq
        )
        cp_prob = h * math.exp(max(prior_lp, -700.0))

        # --- 2. Growth mass per run-length hypothesis ---
        grow_probs = [
            self._run_probs[r] * (1.0 - h) * self._run_predictive(x, r)
            for r in range(n)
        ]

        # --- 3. Assemble new run-length distribution ---
        new_probs = [cp_prob] + grow_probs

        # --- 4. Normalise ---
        total = sum(new_probs)
        if total <= 0.0:
            # Numerical underflow: full reset to prior
            self._run_probs = [1.0]
            self._mu = [self._mu0]
            self._kappa = [self._kappa0]
            self._alpha = [self._alpha0]
            self._beta = [self._beta0]
            return 0.0

        new_probs = [p / total for p in new_probs]

        # --- 5. Update NIG sufficient statistics ---
        # Index 0 (changepoint): update PRIOR with x (first obs in new segment)
        mn0, kn0, an0, bn0 = self._nig_update(
            x, self._mu0, self._kappa0, self._alpha0, self._beta0
        )
        new_mu = [mn0]
        new_kappa = [kn0]
        new_alpha = [an0]
        new_beta = [bn0]

        # Index r+1 (growth): update existing run stats with x
        for r in range(n):
            mn, kn, an, bn = self._nig_update(
                x, self._mu[r], self._kappa[r], self._alpha[r], self._beta[r]
            )
            new_mu.append(mn)
            new_kappa.append(kn)
            new_alpha.append(an)
            new_beta.append(bn)

        # --- 6. Prune low-probability hypotheses ---
        keep = [
            i for i, p in enumerate(new_probs) if p >= self._PRUNE_THRESHOLD
        ]
        if not keep:
            keep = [0]  # always retain changepoint hypothesis

        self._run_probs = [new_probs[i] for i in keep]
        self._mu = [new_mu[i] for i in keep]
        self._kappa = [new_kappa[i] for i in keep]
        self._alpha = [new_alpha[i] for i in keep]
        self._beta = [new_beta[i] for i in keep]

        return new_probs[0]


# ---------------------------------------------------------------------------
# AgreementScorer -- LIVE
# ---------------------------------------------------------------------------


class AgreementScorer:
    """Gates drift alerts behind cross-observer quorum (FIX-2).

    A single-org signal is NEVER promoted to a public drift alert.  A
    quorum of distinct org_ids must independently signal a change on the
    SAME (model_tuple, metric_name) stream, within the candidate TTL
    window, before promote_to_public_alert() returns a non-None count.

    Three properties this class enforces (FIX-2 over the Phase 2 version):

    1. **Metric-scoped agreement.** Candidates are bucketed by
       (model_tuple, metric_name).  Two orgs drifting on different metrics
       of the same model do not agree.

    2. **Candidate TTL.** Each org's most recent candidate counts only
       while newer than ``ttl_ns`` (event-time).  Stale candidates expire,
       so two orgs signalling weeks apart never form a coincidental quorum.

    3. **Population-scaled quorum.** The required quorum is
       ``required_quorum(M)`` where M is the live observer population for
       the stream (distinct orgs seen within the TTL window via
       ``observe()`` or ``ingest()``).  A fixed absolute threshold is
       trivially met as the network grows; q(M) = max(floor, ceil(M/3))
       is the FIX-2b Seismo-bound schedule (flat at the floor for M<=9,
       gentle hedge beyond).  See the module-level policy note.

    ``observe()`` records the watching population; ``ingest()`` records an
    org that actually fired a candidate (and implicitly observes).  The
    effective population is ``max(observers, agreeing)`` so that a caller
    that never calls ``observe()`` degrades safely to the fixed floor.

    On a successful promotion the agreeing candidates for that stream are
    cleared automatically (a fresh drift episode must re-accrue); the
    observer population is retained.

    #SG-TRACE: REQ-ENGINE-008
    #   | assumption: org_id deduplication via dict keys here; Ed25519
    #     org-identity binding (one org = one key) is the upstream gate
    #   | test: test_agreement_scorer_single_org_blocked
    #SG-TRACE: REQ-ENGINE-012
    #   | assumption: agreement is per (model_tuple, metric_name); quorum
    #     scales with the live observer population M
    #   | test: test_agreement_scorer_metric_scoped
    #SG-TRACE: REQ-ENGINE-013
    #   | assumption: candidate/observer TTL is event-time in ns
    #   | test: test_agreement_scorer_ttl_expiry
    """

    QUORUM_MIN: int = 2
    """Legacy Phase 2 absolute quorum.  Retained for backward-compatible
    imports only.  FIX-2 uses QUORUM_FLOOR (3) as the scaled-quorum floor;
    pass ``quorum=`` to override the floor."""

    def __init__(
        self,
        quorum: int | None = None,
        ttl_ns: int = DEFAULT_TTL_NS,
        frac_num: int = QUORUM_FRAC_NUM,
        frac_den: int = QUORUM_FRAC_DEN,
    ) -> None:
        """Initialise the agreement scorer.

        Args:
            quorum: Override for the quorum FLOOR (minimum q(M)).  Defaults
                to QUORUM_FLOOR (3) if None.  The floor is the smallest
                quorum ever required, independent of population size.
            ttl_ns: Candidate/observer expiry window in nanoseconds.
                Defaults to DEFAULT_TTL_NS (14 days).
            frac_num: Numerator of the proportional quorum term.
            frac_den: Denominator of the proportional quorum term.
        """
        self.floor: int = quorum if quorum is not None else QUORUM_FLOOR
        self.ttl_ns: int = ttl_ns
        self.frac_num: int = frac_num
        self.frac_den: int = frac_den
        # (model_tuple, metric_name) -> {org_id: latest_candidate_ts_ns}
        self._agree: dict[tuple[str, str], dict[str, int]] = {}
        # (model_tuple, metric_name) -> {org_id: latest_observed_ts_ns}
        self._observers: dict[tuple[str, str], dict[str, int]] = {}

    @property
    def quorum(self) -> int:
        """Backward-compatible alias: the scaled-quorum floor."""
        return self.floor

    @staticmethod
    def _now_ns() -> int:
        """Wall-clock event-time in nanoseconds."""
        return time.time_ns()

    def observe(
        self,
        model_tuple: str,
        metric_name: str,
        org_id: str,
        timestamp_ns: int | None = None,
    ) -> None:
        """Record that ``org_id`` is watching this stream (population M).

        Called on every accepted signal (drift or not) on the public path.
        Distinct observers within the TTL window define M, which sets the
        required quorum q(M).

        Args:
            model_tuple: Composite model identifier.
            metric_name: Metric stream being observed.
            org_id: Pseudonymous observer identity.
            timestamp_ns: Event-time; defaults to now.

        #SG-TRACE: REQ-ENGINE-012
        #   | test: test_agreement_scorer_quorum_scales_with_population
        """
        ts = timestamp_ns if timestamp_ns else self._now_ns()
        bucket = self._observers.setdefault((model_tuple, metric_name), {})
        prev = bucket.get(org_id, 0)
        if ts >= prev:
            bucket[org_id] = ts

    def ingest(self, result: ChangePointResult) -> None:
        """Record a change-point candidate from one or more orgs.

        Only ``change_detected`` results contribute to quorum; a result
        with ``change_detected=False`` still registers the orgs as
        observers (they are watching but did not fire).

        Args:
            result: A ChangePointResult carrying model_tuple, metric_name,
                contributing_orgs, and (optionally) timestamp_ns.
        """
        if not result.contributing_orgs:
            return
        ts = result.timestamp_ns if result.timestamp_ns else self._now_ns()
        key = (result.model_tuple, result.metric_name)
        for org_id in result.contributing_orgs:
            self.observe(result.model_tuple, result.metric_name, org_id, ts)
            if result.change_detected:
                bucket = self._agree.setdefault(key, {})
                prev = bucket.get(org_id, 0)
                if ts >= prev:
                    bucket[org_id] = ts

    def _live_orgs(self, table: dict[str, int], now_ns: int) -> set[str]:
        """Return orgs whose latest timestamp is in the window (now-ttl, now].

        A candidate is live iff ``cutoff <= ts <= now``: within the last TTL
        and not in the future relative to the evaluation instant.
        """
        cutoff = now_ns - self.ttl_ns
        return {org for org, ts in table.items() if cutoff <= ts <= now_ns}

    def promote_to_public_alert(
        self,
        model_tuple: str,
        metric_name: str = "",
        now_ns: int | None = None,
    ) -> int | None:
        """Return agreeing-org count if population-scaled quorum is met.

        Counts distinct orgs with a live (within-TTL) candidate on the
        (model_tuple, metric_name) stream, computes the required quorum
        from the live observer population M, and promotes if the agreeing
        count meets it.  On promotion the agreeing candidates are cleared;
        observers are retained.

        Args:
            model_tuple: Composite model identifier to evaluate.
            metric_name: Metric stream to evaluate.  Empty string matches
                the unspecified/legacy bucket.
            now_ns: Event-time reference for TTL; defaults to now.

        Returns:
            int count of distinct live agreeing orgs if >= q(M), else None.

        #SG-TRACE: REQ-ENGINE-012
        #   | test: test_single_org_noise_blocked
        #   | test: test_agreement_scorer_quorum_scales_with_population
        """
        key = (model_tuple, metric_name)
        agree_tbl = self._agree.get(key)
        if not agree_tbl:
            return None
        now = now_ns if now_ns is not None else self._now_ns()

        live_agree = self._live_orgs(agree_tbl, now)
        if not live_agree:
            return None
        obs_tbl = self._observers.get(key, {})
        live_obs = self._live_orgs(obs_tbl, now)
        population = max(len(live_obs), len(live_agree))
        q = required_quorum(
            population, self.floor, self.frac_num, self.frac_den
        )
        if len(live_agree) >= q:
            count = len(live_agree)
            self.clear(model_tuple, metric_name)
            return count
        return None

    def clear(self, model_tuple: str, metric_name: str = "") -> None:
        """Clear pending agreeing candidates for a stream after a decision.

        The observer population for the stream is retained (those orgs are
        still watching); only the agreeing-candidate set is discarded so a
        fresh drift episode must re-accrue quorum.

        Args:
            model_tuple: The model identifier to discard candidates for.
            metric_name: The metric stream to discard candidates for.
        """
        self._agree.pop((model_tuple, metric_name), None)
