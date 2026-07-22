#!/usr/bin/env python3
"""Seismo bound: analytical q(M) schedule for the AgreementScorer.

Replaces the hand-picked frac=1/2 with a quorum schedule derived from an
explicit false-positive / detection-power model. No RNG: every number is an
exact binomial tail via math.comb, so the run is fully deterministic and
reproducible (no seed, no Monte-Carlo variance).

Model
-----
For one (model_tuple, metric_name) stream watched by M distinct observer orgs,
inside a candidate-TTL window:

  * Under the NULL (no real drift) each org independently emits a false
    change-point candidate with probability p (per-org, per-TTL-window).
    Coincident false candidates:  X ~ Binomial(M, p).
    Public false-positive per window:  FP(M,q,p) = P(X >= q).

  * Under a REAL provider-side drift, each org that is watching detects it
    with probability d (per-org detection rate inside the window).
    Agreeing detectors:  Y ~ Binomial(M, d).
    Detection power:  POW(M,q,d) = P(Y >= q).

A public alert promotes when >= q of M orgs hold a live candidate on the same
metric within the TTL window. The quorum q(M) must satisfy BOTH:

    FP(M,q,p)  <= beta        (suppress coincidental false alarms)
    POW(M,q,d) >= 1 - gamma   (still surface genuine minority-detected drift)

=> feasible band  q_min(M,p,beta) <= q <= q_max(M,d,gamma).

Correlation-first invariant is a hard floor: q >= 2 always (a single org is
NEVER promoted). The shipped engine floor is 3.

Independence caveat (stated, not hidden): the null model assumes org false
candidates are independent. A provider-side NON-drift event that nudges many
orgs at once (shared upstream, cache flush) is positively correlated and
inflates the real FP above this bound. That is exactly what reputation
weighting + one-org-one-key binding (Phase 2) address; this layer bounds the
INDEPENDENT-noise case, which is the floor of the problem, not the ceiling.
"""

from __future__ import annotations

import math

M_MAX = 20
HARD_FLOOR = 2  # correlation-first: never promote on a single org

# Sensitivity grid.
P_GRID = [0.001, 0.005, 0.01, 0.02, 0.05]  # per-org stable-window FP rate
D_GRID = [0.3, 0.5, 0.7, 0.9]  # per-org detection rate on real drift
BETA_GRID = [0.01, 0.05]  # public-FP budget per TTL window
GAMMA = 0.10  # miss budget: want power >= 0.90


def binom_sf_ge(m: int, q: int, prob: float) -> float:
    """Exact P(Binom(m, prob) >= q) via math.comb (no float comb error)."""
    if q <= 0:
        return 1.0
    if q > m:
        return 0.0
    total = 0.0
    for i in range(q, m + 1):
        total += math.comb(m, i) * (prob**i) * ((1.0 - prob) ** (m - i))
    return total


def q_min_fp(m: int, p: float, beta: float) -> int | None:
    """Smallest q in [HARD_FLOOR, m] with FP(m,q,p) <= beta. None if none."""
    for q in range(max(1, HARD_FLOOR), m + 1):
        if binom_sf_ge(m, q, p) <= beta:
            return q
    return None


def q_max_power(m: int, d: float, gamma: float) -> int:
    """Largest q in [0, m] with POW(m,q,d) >= 1-gamma. 0 if even q=1 fails."""
    best = 0
    for q in range(1, m + 1):
        if binom_sf_ge(m, q, d) >= (1.0 - gamma):
            best = q
    return best


def shipped_q(m: int, floor: int = 3, num: int = 1, den: int = 2) -> int:
    """Engine's current required_quorum: max(floor, ceil(num*m/den))."""
    scaled = (num * m + den - 1) // den
    return max(floor, scaled)


def band_line(m: int, p: float, d: float, beta: float) -> str:
    qmn = q_min_fp(m, p, beta)
    qmx = q_max_power(m, d, GAMMA)
    ship = shipped_q(m)
    qmn_s = "--" if qmn is None else str(qmn)
    feasible = qmn is not None and qmn <= qmx and qmx >= HARD_FLOOR
    ship_ok = (
        qmn is not None
        and ship >= qmn  # suppresses FP
        and ship <= qmx  # keeps power
    )
    flag = "OK " if feasible else "XX "
    ship_flag = "ship-ok" if ship_ok else "SHIP-FAILS"
    return (
        f"  M={m:>2}  q_min(FP)={qmn_s:>2}  q_max(POW)={qmx:>2}  "
        f"shipped={ship:>2}  band={flag}{ship_flag}"
    )


def recommend_frac(p: float, d: float, beta: float) -> tuple[int, int, str]:
    """Find the gentlest single proportional frac num/den (num<=den<=6, plus
    a couple of common shapes) whose closed form max(3, ceil(num*M/den)) stays
    inside [q_min, q_max] for every feasible M. Returns (num, den, verdict)."""
    candidates = [
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (1, 6),
        (2, 5),
        (2, 7),
        (1, 8),
        (1, 10),
    ]
    for num, den in candidates:
        ok_all = True
        any_feasible = False
        for m in range(2, M_MAX + 1):
            qmn = q_min_fp(m, p, beta)
            qmx = q_max_power(m, d, GAMMA)
            if qmn is None or qmn > qmx:
                continue  # M infeasible for anyone; skip
            any_feasible = True
            q = shipped_q(m, floor=3, num=num, den=den)
            if not (qmn <= q <= qmx):
                ok_all = False
                break
        if ok_all and any_feasible:
            return num, den, "fits"
    return 0, 0, "no single frac fits — table lookup needed"


def main() -> None:
    print("=" * 72)
    print("SEISMO BOUND — analytical q(M) schedule")
    print(
        "HARD_FLOOR (correlation-first) =",
        HARD_FLOOR,
        "| GAMMA (miss budget) =",
        GAMMA,
        "-> power >= 0.90",
    )
    print("shipped policy: q(M) = max(3, ceil(M/2))")
    print("=" * 72)

    # 1. Full band scan at a representative operating point.
    p0, d0, beta0 = 0.02, 0.7, 0.05
    print(f"\n[1] Band scan @ p={p0}, d={d0}, beta={beta0}, power>=0.90")
    for m in range(2, M_MAX + 1):
        print(band_line(m, p0, d0, beta0))

    # 2. Where does shipped ceil(M/2) fall out of band? Sweep the grid.
    print("\n[2] Shipped max(3,ceil(M/2)) — does it stay in [q_min,q_max]?")
    print("    (SHIP-FAILS = shipped quorum is outside the feasible band)")
    fail_rows = []
    for p in P_GRID:
        for d in D_GRID:
            for beta in BETA_GRID:
                fails = []
                for m in range(2, M_MAX + 1):
                    qmn = q_min_fp(m, p, beta)
                    qmx = q_max_power(m, d, GAMMA)
                    if qmn is None or qmn > qmx:
                        continue  # nobody can satisfy both here
                    ship = shipped_q(m)
                    if not (qmn <= ship <= qmx):
                        reason = "FP" if ship < qmn else "POWER"
                        fails.append((m, ship, qmn, qmx, reason))
                if fails:
                    fail_rows.append((p, d, beta, fails))
    if not fail_rows:
        print("    shipped policy stays in band across the ENTIRE grid.")
    else:
        for p, d, beta, fails in fail_rows:
            ms = ", ".join(
                f"M={m}(ship {s} vs [{lo},{hi}] {why})"
                for (m, s, lo, hi, why) in fails
            )
            print(f"    p={p} d={d} beta={beta}: {ms}")

    # 3. Recommended gentlest frac per operating point.
    print("\n[3] Gentlest closed-form frac that stays in band (floor=3):")
    for p in P_GRID:
        for d in D_GRID:
            for beta in BETA_GRID:
                num, den, verdict = recommend_frac(p, d, beta)
                shape = f"{num}/{den}" if num else "----"
                print(
                    f"    p={p:<5} d={d:<3} beta={beta:<4} -> "
                    f"frac={shape:<5} ({verdict})"
                )

    # 4. Detection power of the shipped policy at the operating point.
    print(
        f"\n[4] Shipped-policy detection power @ d={d0} (per-org detect rate):"
    )
    for m in (3, 5, 7, 10, 15, 20):
        ship = shipped_q(m)
        pw = binom_sf_ge(m, ship, d0)
        fp = binom_sf_ge(m, ship, p0)
        print(
            f"    M={m:>2}  shipped q={ship:>2}  POWER(d={d0})={pw:6.3f}  "
            f"FP(p={p0})={fp:.2e}"
        )


# ----------------------------------------------------------------------------
# Anchoring p to the CUSUM ARL0, TTL feasible band, and the recommended
# calibrated schedule.
# ----------------------------------------------------------------------------

ARL0 = 500.0  # obs between false alarms, CUSUM h=5/k=0.5 (Page 1954)
D_ONSET_SPREAD = 5  # days: backtest onset 2025-08-05 -> first alert 08-10


def p_of_window(
    cadence_per_day: float, ttl_days: float, arl0: float = ARL0
) -> float:
    """Per-org window-FP: lam = c*T/ARL0 false alarms; p = 1-e^-lam."""
    lam = cadence_per_day * ttl_days / arl0
    return 1.0 - math.exp(-lam)


def q_min_table(p: float, beta: float, m_max: int = M_MAX) -> list[int]:
    """Calibrated schedule q(M) = max(3, q_min_FP(M|p,beta)) for M=1..m_max."""
    out = []
    for m in range(1, m_max + 1):
        qmn = q_min_fp(m, p, beta)
        q = 3 if qmn is None else max(3, qmn)
        out.append(min(q, m) if m >= 1 else q)
    return out


def anchoring() -> None:
    print("\n" + "=" * 72)
    print("ANCHORING p TO CUSUM ARL0 + TTL BAND")
    print("=" * 72)
    print(
        f"ARL0 = {ARL0:.0f} obs/false-alarm (h=5/k=0.5); TTL accumulates risk."
    )

    print(
        "\n[A] p(window) as a function of per-metric canary cadence, TTL=14d:"
    )
    for c in (0.25, 0.5, 1.0, 2.0, 4.0, 24.0):
        p = p_of_window(c, 14.0)
        print(
            f"    cadence={c:>5}/day  ->  "
            f"lam={c * 14 / ARL0:6.3f}  p(14d)={p:6.4f}"
        )

    print(
        "\n[B] TTL feasible band (target p<=0.05 keeps floor-3 table valid):"
    )
    for c in (0.5, 1.0, 2.0):
        # upper bound: solve c*T/ARL0 = -ln(1-0.05) -> T = ARL0*ln(1/0.95)/c
        t_max = ARL0 * math.log(1.0 / 0.95) / c
        print(
            f"    cadence={c:>4}/day  lower=D_spread~{D_ONSET_SPREAD}-14d  "
            f"upper(p<=0.05)={t_max:6.1f}d  -> 14d in band: "
            f"{'YES' if D_ONSET_SPREAD <= 14 <= t_max else 'NO'}"
        )

    print(
        "\n[C] Recommended calibrated schedule at the anchored operating point"
    )
    p_op = p_of_window(1.0, 14.0)  # cadence ~1/day, TTL 14d
    beta = 0.05
    print(f"    p_op = p(cadence=1/day, TTL=14d) = {p_op:.4f}; beta={beta}")
    tbl = q_min_table(p_op, beta)
    ship = [shipped_q(m) for m in range(1, M_MAX + 1)]
    print(
        "     M : 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20"
    )
    print("  calib: " + " ".join(f"{q:>2}" for q in tbl))
    print("  shipd: " + " ".join(f"{q:>2}" for q in ship))
    # power comparison at d=0.7
    print("\n[D] Power(d=0.7) — calibrated vs shipped:")
    for m in (3, 5, 7, 10, 15, 20):
        qc = tbl[m - 1]
        qs = ship[m - 1]
        pwc = binom_sf_ge(m, qc, 0.7)
        pws = binom_sf_ge(m, qs, 0.7)
        fpc = binom_sf_ge(m, qc, p_op)
        print(
            f"    M={m:>2}  calib q={qc} POWER={pwc:5.3f} FP={fpc:.1e}  |  "
            f"shipped q={qs} POWER={pws:5.3f}"
        )


if __name__ == "__main__":
    main()
    anchoring()
