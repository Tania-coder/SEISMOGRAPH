---
name: measure-first
description: Use whenever a conclusion is about to be drawn from data, logs, benchmarks, test output or metrics — before stating that something changed, improved, regressed, or is "fine". Forces a denominator, a noise floor, and a cheap verification before any claim.
---

# Measure first

A working discipline from SEISMOGRAPH, an open-source drift detector for
LLM APIs. Every rule below was earned by being wrong first. The
refutations are included, because a rule without its counter-example is
just an opinion.

Apply this whenever you are about to tell the user that something moved,
broke, improved, regressed, passed, or is fine.

## 1. No rate without its denominator and its window

Never write "97%", "most", "usually" or "the error rate dropped" without
saying **out of how many** and **over what period**, in the same
sentence.

- Bad: "JSON validity is 97%."
- Good: "JSON validity is 97% — 291 of 300 responses, collected over
  six days."

If you do not have the denominator, say that instead of the rate.

> Earned: a dashboard published rates with no base for weeks. Its owner
> could not see a 56-hour outage through them, because every counter
> read `10/10` — the missing rows had never been written, and a counter
> cannot see a row that does not exist. Only elapsed time found it.

## 2. Establish the noise floor before you call anything a signal

"It moved by 40%" is meaningless until you know how much it moves when
**nothing** changed. Before reporting a difference between two states,
ask whether the same measurement has been repeated against an unchanged
state — and if it has not, say so, or run it.

The floor is often surprising. Two runs of an identical, unchanged
system may agree far less than anyone expects.

Report differences as: measured difference, **against** the floor.

> Earned: the same model, same questions, same settings, one hour
> apart, agreed with itself about 60% of the time. Without that number,
> a 57% agreement with a different model would have looked like a
> finding. It was noise.

## 3. Ask why the missing data is missing

Before concluding anything from a dataset with gaps, ask what caused the
gaps — and whether that cause is **connected to the thing being
measured**. If it is, the sample is not merely smaller. It means
something different.

> Earned: probe runs were discarded when a request hit a rate limit.
> Rate limits happen when a provider is under load. Provider load is
> exactly when behaviour is most likely to change. The data was missing
> precisely the moments worth measuring.

## 4. The obvious fingerprint is often the wrong one

When choosing what to compare, do not default to exact equality. Exact
match is brittle and frequently cannot separate the cases you care
about. Check whether a distributional summary — a mean, a length, a
rate — separates them more cleanly, and prefer whichever actually does.

State which one you used and why.

> Earned: counting byte-identical answers could not distinguish a
> different model from the same model an hour later; the ranges
> overlapped. Mean output length separated them with no overlap at all.

## 5. Verify before asserting, when verification is cheap

If a claim can be checked in under a minute — run the command, read the
file, count the rows — **check it first and say nothing until the check
returns**. Do not narrate the hypothesis on the way.

Prefer: run it, then report. Never: "this is probably X, let me check."

> Earned: five confident conclusions in two sessions were each killed by
> a measurement that took under a minute.

## 6. Put the verdict last

When running a gate, a test suite, a linter or a build, arrange the
output so the **verdict is the final line on screen**. A result the
reader scrolls past is not a result.

If several checks run, print a single explicit PASS/FAIL summary after
all of them.

> Earned: a repository was pushed with a failing gate. The linter had
> reported an error, but three checks were chained and its line sat
> above "345 passed" — the last thing on screen was the one check that
> succeeded, so the run read as green.

## 7. Record what a measurement refuted

When new data kills an earlier conclusion — including one you stated
yourself, minutes ago — write the refutation down where the conclusion
lived. Do not quietly stop mentioning it.

Say plainly: this was concluded, this measurement refutes it, it is
withdrawn.

> Earned: "some categories of prompt are inherently unstable" survived
> two hours. Three more runs showed the same category was perfectly
> stable on a different model. Instability was a property of the model,
> not the category.

## 8. Never show green for "I don't know"

Do not report success, health or stability when what you actually have
is an absence of evidence. Add a third state — unknown, stale, not
measured — and use it.

A status that guesses green is worse than no status.

> Earned: a public board showed STABLE for a model whose newest data
> was 176 hours old, and for a model that had never sent any data at
> all. The status was computed only from "no alert raised" — and with a
> single observer, no alert could ever be raised.

---

Written by Tatiana Radchenko while building SEISMOGRAPH.
github.com/Tania-coder/SEISMOGRAPH · Apache-2.0 · take it, change it.
