# Contributing to SEISMOGRAPH

Thanks for your interest. SEISMOGRAPH is maintained by a single maintainer
(Tetiana Radchenko); small, focused contributions are the easiest to review.

## Reporting bugs and proposing changes

- **Bugs / feature requests:** open a GitHub Issue with steps to reproduce
  (or a concrete use case). Expect an initial response within 14 days.
- **Security issues:** do NOT open a public issue — follow
  [SECURITY.md](SECURITY.md).

## Pull requests

1. Fork and create a branch named `seismograph/task-{short-id}`. Never
   commit to `main` directly.
2. Keep PRs small and single-purpose.
3. **Tests are mandatory for functional changes.** Any major new
   functionality must come with tests added to the automated suite
   (`tests/`), and all existing tests must pass.
4. Local gate before pushing (both must be clean):

   ```
   pip install ruff==0.15.20
   ruff check . && ruff format --check .
   python -m pytest -q
   ```

5. CI (pytest + ruff + CodeQL) must be green; PRs are squash-merged.

## Architectural invariants (PRs violating these are declined)

- **Privacy by construction:** raw prompts/outputs never leave the probe
  perimeter — only hashes, distributional features, and DP-noised
  aggregates are transmitted.
- **Content-addressed baselines:** canary suites are immutable and
  hash-addressed; never mutate a historical baseline — add a new version.
- **Correlation-first alerts:** a single-org signal is never promoted to a
  public drift alert; cross-observer quorum gates every public alert.
- **Canary cost cap:** the suite stays ≤200 prompts and cheap to run.
- **Standard crypto only:** cryptography via well-known libraries
  (Ed25519, SHA-256); no custom cryptographic primitives.

## Code style

Python 3.10+, `ruff` (pinned version above) for linting and formatting.
Non-trivial blocks carry a `#SG-TRACE:` comment linking requirement,
assumption, and covering test — follow the existing pattern.

## License

By contributing you agree your contributions are licensed under the
[Apache License 2.0](LICENSE).
