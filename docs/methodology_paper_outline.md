# SEISMOGRAPH Methodology Paper — Outline

Status: OUTLINE v0.1 (Phase 2 tail). Owner: Tatiana. Drafted 2026-07-14.
Purpose: grant credibility + Tier-A outreach artifact. Canon: E1 facts only
(memory/CURRENT_STATE.md); locked phrasing for the backtest result.

---

## Working title

**SEISMOGRAPH: Federated, Privacy-Preserving Early Warning for Silent
Behavioural Drift in Third-Party LLM APIs**

Alternates:
- "Is It Me, My Prompt, or the Model? Detecting Silent LLM API Drift Without
  Sharing Prompts"
- "A Seismograph for Model Weather: CUSUM-Based Drift Detection over
  Differentially Private Canary Aggregates"

## Candidate venues

1. **arXiv preprint — cs.SE, cross-list cs.LG + cs.CR.** Primary home; citable
   immediately alongside the Zenodo record (10.5281/zenodo.21045517); no
   gatekeeping delay for grant deadlines. cs.SE fits: this is monitoring
   infrastructure for deployed systems, not a new learning method.
2. **CAIN (International Conference on AI Engineering, ICSE co-located) or an
   SE4AI-track workshop.** Best topical fit (engineering of AI-based systems,
   MLOps/monitoring); workshop tracks are realistic for an independent OSS
   researcher with a single case study. [verify current CFP + dates]
3. **A NeurIPS/ICML workshop on reliable/deployed ML, or EuroMLSys.** Higher
   visibility with the monitoring/observability research crowd; workshop
   papers accept preliminary evaluations honestly framed. [verify which
   workshops run this cycle before committing]

Fallback/practitioner channel (not peer review, still credibility): SREcon or
QCon talk derived from the paper.

---

## Abstract (draft, one paragraph — canon-compliant)

Production systems increasingly depend on third-party LLM APIs whose behaviour
can shift without any change to latency, uptime, or status codes — and without
a changelog. We present SEISMOGRAPH, an open-source, federated early-warning
network for such silent drift. Each participating organisation runs a
lightweight probe that executes a versioned, content-addressed canary suite
(<=200 prompts, temperature 0) against the APIs it depends on; raw prompts and
outputs never leave the probe perimeter — only hashed identifiers,
distributional features, and differentially private aggregates (Laplace
mechanism, epsilon=2.0 per flush) are transmitted. A central correlation
engine applies Page-CUSUM change-point detection per (model, metric) stream
and gates every public alert behind cross-observer agreement (quorum >= 2
pseudonymous, Ed25519-identified probes), so no single observer can raise a
public alarm. We evaluate the pipeline on a reconstruction of the Anthropic
Aug-Sep 2025 incident, in which three infrastructure bugs — not a model
update — silently degraded Claude output quality (postmortem 2025-09-17). We
model the first bug, a context-window routing error affecting Claude Sonnet 4
(~0.8% of requests from 2025-08-05, ~16% from 2025-08-29), with seeded
synthetic canary metrics: a seeded backtest flags it 38 days before the
postmortem (first alert 2025-08-10, 19 days before the escalation), while the
misrouting rate was still 0.8%. We release the full system, the backtest
(SEED=42), and a 127-test suite under Apache-2.0.

---

## 1. Introduction

- Problem: silent behavioural drift in LLM/agent APIs is invisible to
  infrastructure monitoring (200 OK, normal latency); teams discover it late,
  alone, in production. [EXISTS: docs/product/VISION.md, README.md]
- Core question the system answers: "Is it me, my prompt, or did the model
  change?" [EXISTS: SEISMOGRAPH_Architecture.md sec 1]
- Why federation: one org's signal is statistically weak and unverifiable;
  cross-observer agreement turns anecdote into evidence. [EXISTS: arch sec 7]
- Why privacy-by-construction is the adoption precondition: orgs will not
  share prompts/outputs; the design must make leakage structurally hard.
  [EXISTS: docs/arch/ADR/0001-privacy-first-architecture.md]
- Contributions list: (1) probe + privacy layer design, (2) two-layer
  detection (CUSUM + quorum), (3) seeded backtest case study of a real,
  publicly documented incident, (4) OSS release + reproducibility.
  [NEEDS WORK: crisp 4-bullet contributions wording]

## 2. Related work

Candidate directions only — ALL to be verified against literature; no
citations committed yet.

- Statistical drift/change-point detection: Page-CUSUM lineage, Bayesian
  online change-point detection (Adams & MacKay line), data/concept drift in
  ML monitoring. [NEEDS WORK: literature pass; position CUSUM choice]
- LLM monitoring/observability & regression testing: behavioural test suites,
  "model updates break prompts" studies, eval-in-production tooling, OTel
  GenAI semantic conventions. [NEEDS WORK: survey + differentiate: we target
  cross-org silent drift, not single-org eval]
- Differentially private aggregation and telemetry: Laplace mechanism, DP
  telemetry deployments, budget accounting. [NEEDS WORK: verify epsilon
  framing against established DP telemetry practice]
- Federated analytics (not federated learning): cross-org aggregate statistics
  without raw-data sharing; Sybil resistance in open reporting networks.
  [NEEDS WORK: identify 3-5 anchor papers]
- Canary-based testing in SRE practice: canary releases, synthetic
  monitoring — framing bridge for practitioner readers. [NEEDS WORK: writing]

## 3. Threat model

- Adversaries considered: (a) curious aggregator (honest-but-curious central
  engine), (b) malicious observer injecting fabricated signals (Sybil), (c)
  passive network observer, (d) provider ToS constraints as a deployment
  boundary. [EXISTS: partially in arch secs 4, 7, 10; ADR 0001]
- Privacy goal: raw prompts/outputs never leave the probe perimeter;
  transmitted data limited to hashes, distributional features, DP aggregates.
  [EXISTS: probe/privacy.py SignalBatch; enforced invariant]
- Integrity goal: no single org can force a public alert (quorum), replay
  dedup within scoring rounds, Ed25519 probe identity with reputation
  weighting planned. [EXISTS: engine/correlation.py AgreementScorer,
  probe/crypto.py KeyManager]
- Out of scope: compromised probe host, provider-side adversary, key
  revocation (explicitly deferred). [NEEDS WORK: write the scoping honestly;
  note gateway/auth.py signature verification is a stub in evaluated version]

## 4. System design

### 4.1 Probe & canary suites
- Versioned, content-addressed canary suites (SHA-256 over canonicalised
  prompts); append-only registry; staleness warnings distinct from drift
  alerts. [EXISTS: probe/canary_suite.py, arch sec 5]
- Cost cap <=200 prompts, temperature 0; per-day cost target. [EXISTS: arch]
- OTel-native instrumentation plan (gen_ai.*, mcp.*). [EXISTS: probe/sdk.py
  interface; NEEDS WORK: honest status — OTel wiring is Phase 1, stub today]

### 4.2 Privacy layer
- Metrics reduced to distributional features per (model_tuple, metric);
  Laplace DP noise, epsilon=2.0 per flush window; DPAccountant with persisted
  budget, flush-interval recommendation. [EXISTS: probe/privacy.py Aggregator,
  DPAccountant]
- Frozen SignalBatch schema; Pydantic ingest validation (frozen + forbid).
  [EXISTS: probe/privacy.py, gateway/schema.py]
- [NEEDS WORK: sensitivity analysis writeup — how delta_f was chosen per
  metric; sequential composition accounting is an open Phase 1 item — state
  it as such]

### 4.3 Correlation engine
- Per-org, per-metric Page-CUSUM (engine/detector.py): standardised z,
  S+/S- recursions, h=5.0, k=0.5, baseline_samples=30 with documented
  calibration defect record (D9). [EXISTS: engine/detector.py,
  data/drift_labels/cusum_phase0_calibration.md]
- Cross-org quorum: AgreementScorer, QUORUM_MIN=2, distinct-org union over
  ChangePointResult. [EXISTS: engine/correlation.py]
- Bayesian online change-point detector as a second detector family.
  [EXISTS: engine/correlation.py BayesianOnlineDetector implementation;
  NEEDS WORK: confirm status vs arch doc (arch says stub) and either evaluate
  it or scope it out of the paper]

## 5. Detection method

- Why CUSUM for this signal shape: small persistent mean shift (0.8%
  misrouting) under Gaussian-ish noise; sensitivity vs ARL trade-off via
  (h, k). [EXISTS: arch sec 6; NEEDS WORK: brief formal treatment + ARL/false
  -positive-rate estimate for h=5, k=0.5]
- Baseline estimation pitfalls: sigma0 underestimation with short baselines
  (documented D9 defect, 10 -> 30 samples). Honest inclusion — this is a
  strength. [EXISTS: calibration record]
- Two-layer promotion: candidate DriftAlert -> quorum gate -> public alert;
  single-org signals stay private. [EXISTS: code + arch]
- [NEEDS WORK: sensitivity study — alert date vs h, k, baseline_samples,
  noise sigma, and DP noise on/off. This is THE missing experiment.]

## 6. Evaluation: seeded backtest case study

- Incident: Anthropic postmortem 2025-09-17 — THREE infrastructure bugs, not
  a model update (Anthropic explicit). Backtest models bug #1: context-window
  routing error, Claude Sonnet 4, ~0.8% affected from 2025-08-05, ~16% from
  2025-08-29. [EXISTS: scripts/anthropic_backtest.py,
  notebooks/anthropic_backtest_report.md]
- Setup: seeded (SEED=42) synthetic daily canary metrics (json_success_rate,
  avg_output_length) with phase-wise Gaussian parameters reconstructed from
  the public postmortem timeline. [EXISTS: backtest script]
- Result, locked phrasing: a seeded backtest flags it 38 days before the
  postmortem (first alert 2025-08-10, S-=7.278 > h=5.0; 19 days before the
  escalation; detected in the subtle 0.8% phase). NEVER phrase as a live
  catch. [EXISTS: report + assertions C1-C6; re-confirmed live S035]
- Reproducibility: single script, fixed seed, asserted in the 127-test suite.
  [EXISTS: tests; CI green]
- [NEEDS WORK: DP-noise-on variant of the backtest (report currently notes
  ~1-3 day expected delay but does not run it); multi-observer simulation
  (N>=2 probes with independent noise) to exercise the quorum path end-to-end]

## 7. Limitations (honest, load-bearing for credibility)

- Single simulated observer: the quorum mechanism is designed and tested in
  unit form but the headline backtest is a one-org simulation; a live public
  alert requires >= 2 orgs.
- Synthetic data reconstructed from a public postmortem: phase parameters are
  plausible reconstructions, not measured provider traffic; real lead time
  may be shorter or longer.
- One incident, one metric family: no claim of generality across incident
  types (e.g., quality drift without JSON-validity signal).
- DP calibration not externally audited: epsilon=2.0 and sensitivity bounds
  are internal choices; sequential composition accounting still open.
- Backtest ran without DP noise; live noise adds variance and may delay
  alerts (estimated 1-3 days, unverified).
- Ed25519 signature verification stubbed at the gateway in the evaluated
  version; Sybil resistance beyond per-round dedup is future work.

## 8. Reproducibility statement

- Everything public: Apache-2.0 repo, pip package (seismograph-probe), Zenodo
  archive — cite concept DOI 10.5281/zenodo.21045517. [EXISTS: repo, PyPI,
  Zenodo v1.0.1 with corrected Sonnet 4 wording]
- One-command backtest: python3 scripts/anthropic_backtest.py (SEED=42);
  report regenerated deterministically; 127 tests pass. [EXISTS]
- Canary suites content-addressed (SHA-256) for exact re-execution. [EXISTS]
- [NEEDS WORK: pin an environment (requirements lock or container ref) in the
  paper's artifact appendix; state Python version]

---

## Next concrete steps (ordered)

1. Run the DP-noise-on backtest variant + (h, k, baseline_samples, sigma)
   sensitivity grid; one figure + one table. Biggest evidence gap, ~1 script.
2. Multi-observer quorum simulation (2-3 synthetic probes, independent
   seeds) to demonstrate the promotion path end-to-end.
3. Resolve BayesianOnlineDetector status (evaluate as comparison detector or
   explicitly scope out) — arch doc and code currently disagree.
4. Literature pass for Section 2 (drift detection, LLM observability, DP
   telemetry, federated analytics); verify all citations, none committed yet.
5. Draft Sections 6-7 first (evaluation + limitations — strongest, most
   canon-sensitive material), then 3-5, then intro/abstract polish.
6. Verify CAIN / workshop CFP dates; pick primary target; format skeleton
   (arXiv LaTeX) and land the outline into it.
