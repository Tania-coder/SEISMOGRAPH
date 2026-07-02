# SEISMOGRAPH — Vision

**A smoke detector for the models the world now runs on.**

## The problem we are solving

The software industry has quietly moved its most important logic onto LLM APIs
it does not control. These models change — silently, with no changelog, often
without the provider announcing it. When behaviour shifts, the failure is
invisible to every existing monitor: latency is fine, uptime is 100%, the
endpoint returns 200. Teams discover the drift only after it has already reached
their users.

Today there is no shared, neutral early-warning layer for this. Every team
re-discovers each silent change alone, late, and in production.

## Mission (2-year horizon)

Make silent LLM/agent drift a **detected, shared signal** instead of a private
2am surprise. Within two years, a team building on any major model should be able
to glance at a public "model weather" report — or run a private probe inside its
own perimeter — and know within hours whether a model it depends on has shifted
from its baseline, with no raw data ever leaving its walls.

## The world with SEISMOGRAPH

- Every serious LLM application has a **drift sensor** — the way every building
  has a smoke detector: cheap, always-on, and boring until the moment it matters.
- Drift is caught **before users feel it**, not weeks later in a postmortem.
- The early-warning signal is a **public good**: privacy-preserving, federated,
  owned by no single vendor — trust comes from cross-observer agreement, not from
  one company's word.
- "Is it me, my prompt, or did the model change?" stops being unanswerable.

## Principles (non-negotiable)

1. **Privacy by construction.** Raw prompts and outputs never leave the probe.
   Only hashes and DP-noised aggregates are shared. Trust is earned by making
   leakage structurally hard, not by policy promises.
2. **Correlation-first.** No single observer can raise a public alarm. Drift is
   real only when independent probes agree — this resists noise and bad actors.
3. **Public good before product.** The free, open "model weather" layer comes
   first; enterprise features fund it, they do not gate the core signal.
4. **Reproducible or it did not happen.** Every claim — including the 38-day
   backtest — ships with a seed and a script.

## Who it is for

- ML and platform engineers shipping on third-party models.
- Trust & Safety and reliability teams who need behavioural, not just
  infrastructural, monitoring.
- Researchers and grant-funded labs studying model stability over time.

## Why I build this

> _[EDIT — replace with your authentic reason; this is the part grant reviewers
> and interviewers remember. Draft to personalise:]_
>
> I build infrastructure for a living, and the failures that scare me most are
> the silent ones — where every dashboard is green and the ground has moved
> anyway. I believe the reliability layer for AI should be a public good, not a
> private moat. And I wanted to prove that a small, honest team — one engineer
> working with AI tools — can build that layer to a professional standard.
> SEISMOGRAPH is that proof.

---

Maintained by Tatiana Radchenko · Aarhus · Apache-2.0 · roadmap in `ROADMAP.md`
