#!/usr/bin/env python3
"""Pick the gentle-hedge q(M) schedule from the verify worst case.

Constraints a schedule must satisfy:
  (C1) near-term flat: q(M)=3 for M<=6  (calibrated honest optimum;
       identical to shipped there, so no regression in the regime the
       network actually lives in).
  (C2) honest-noise FP ok: binomial FP(M,q | p_op=0.0276) <= beta=0.05.
  (C3) WORST-CASE FP hedge (the verify finding): beta-binomial FP at the
       estimation-inflated p_hi=0.074 (median baseline ARL0~182) with a
       design correlation allowance rho, must stay <= beta at M=10,15,20.
  (C4) power kept: at conservative coverage-discounted d, detection power
       P(Binom(M,d)>=q) must not collapse (>= 0.80 target at d=0.5, and
       q must stay <= q_max(POW, d=0.7)).

We evaluate candidate closed forms and knee forms and pick the GENTLEST
that satisfies C1-C4, preferring a form the engine already supports
(max(floor, ceil(num*M/den))) over a new knee parameterisation.
"""

from __future__ import annotations

import math

BETA = 0.05
P_OP = 0.0276  # anchored honest-noise per-org window FP (cadence 1/day)
P_HI = 0.074  # estimation-inflated (median baseline ARL0 ~182)
RHO = 0.10  # design correlation allowance (verify: crit rho ~0.08 @ p_hi)


def binom_ge(m, q, p):
    if q <= 0:
        return 1.0
    if q > m:
        return 0.0
    return sum(
        math.comb(m, i) * p**i * (1 - p) ** (m - i) for i in range(q, m + 1)
    )


def betabinom_ge(m, q, p, rho):
    """P(X>=q), X~BetaBinomial(m) mean p, intra-class correlation rho.

    rho = 1/(alpha+beta+1) -> alpha+beta = (1-rho)/rho;
    alpha = p*s, beta = (1-p)*s.
    """
    if q <= 0:
        return 1.0
    if q > m:
        return 0.0
    if rho <= 0:
        return binom_ge(m, q, p)
    s = (1.0 - rho) / rho
    a = p * s
    b = (1.0 - p) * s

    # pmf via Beta-Binomial: C(m,i) B(i+a, m-i+b)/B(a,b), using lgamma.
    def lbeta(x, y):
        return math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)

    lbab = lbeta(a, b)
    total = 0.0
    for i in range(q, m + 1):
        lpmf = math.log(math.comb(m, i)) + lbeta(i + a, m - i + b) - lbab
        total += math.exp(lpmf)
    return total


def q_max_power(m, d, gamma=0.10):
    best = 0
    for q in range(1, m + 1):
        if binom_ge(m, q, d) >= 1 - gamma:
            best = q
    return best


# ---- candidate schedules --------------------------------------------------
def frac(m, num, den, floor=3):
    return max(floor, (num * m + den - 1) // den)


def knee(m, floor, knee_at, step):
    return max(floor, floor + max(0, m - knee_at) // step)


CANDS = {
    "flat q=3            ": lambda m: frac(m, 0, 1),
    "ceil(M/6)           ": lambda m: frac(m, 1, 6),
    "ceil(M/5)           ": lambda m: frac(m, 1, 5),
    "ceil(M/4)           ": lambda m: frac(m, 1, 4),
    "ceil(M/3)           ": lambda m: frac(m, 1, 3),
    "knee@8 step6        ": lambda m: knee(m, 3, 8, 6),
    "knee@8 step4        ": lambda m: knee(m, 3, 8, 4),
    "knee@6 step4        ": lambda m: knee(m, 3, 6, 4),
    "shipped ceil(M/2)   ": lambda m: frac(m, 1, 2),
}

MS = list(range(2, 21))


def evaluate():
    print(f"p_op={P_OP}  p_hi={P_HI}  rho={RHO}  beta={BETA}")
    print(
        "Worst-case FP = BetaBinomial(p_hi, rho). "
        "Power at d=0.5 (conservative), and d=0.7.\n"
    )
    hdr = "sched                " + "".join(f"{m:>3}" for m in MS)
    print(hdr)
    for name, fn in CANDS.items():
        row = "".join(f"{fn(m):>3}" for m in MS)
        print(name + row)

    print("\nChecks per candidate:")
    print(
        "  C1 flat@M<=6 | C2 honest FP | C3 worstFP@M10/15/20 | "
        "C4 pow d=.5@M10/15/20, q<=qmaxPOW(.7)"
    )
    for name, fn in CANDS.items():
        c1 = all(fn(m) == 3 for m in range(2, 7))
        c2 = all(binom_ge(m, fn(m), P_OP) <= BETA for m in MS)
        wc = {m: betabinom_ge(m, fn(m), P_HI, RHO) for m in (10, 15, 20)}
        c3 = all(v <= BETA for v in wc.values())
        powd5 = {m: binom_ge(m, fn(m), 0.5) for m in (10, 15, 20)}
        c4b = all(
            fn(m) <= q_max_power(m, 0.7)
            for m in MS
            if q_max_power(m, 0.7) >= 3
        )
        verdict = "PASS" if (c1 and c2 and c3) else "----"
        print(
            f"  {name} C1={'Y' if c1 else 'n'} C2={'Y' if c2 else 'n'} "
            f"C3={'Y' if c3 else 'n'}"
            f"[{wc[10]:.3f}/{wc[15]:.3f}/{wc[20]:.3f}] "
            f"C4pow.5=[{powd5[10]:.2f}/{powd5[15]:.2f}/{powd5[20]:.2f}] "
            f"q<=qmax.7={'Y' if c4b else 'n'}  {verdict}"
        )


if __name__ == "__main__":
    evaluate()
