"""
scripts/live_probe.py
=====================
Run the v1.0.0 canary suite against a REAL OpenAI-compatible endpoint and
print the privacy-preserving results. This is the first live, end-to-end
proof that the probe works against a real model -- not a mock.

It speaks the OpenAI-compatible Chat Completions API, so it works with:
  - a local Ollama         (free, no key):  base_url http://localhost:11434/v1
  - OpenAI / Groq / Mistral / Together (hosted): set base_url + api_key

Configuration (environment variables, all optional except as noted):
  SEISMOGRAPH_PROBE_BASE_URL    default http://localhost:11434/v1
  SEISMOGRAPH_PROBE_API_KEY     bearer token (omit for local Ollama)
  SEISMOGRAPH_PROBE_MODEL_TUPLE default ollama/llama3.1
  SEISMOGRAPH_PROBE_MAX_TOKENS  default 64

Privacy: only SHA-256 hash, output length, json_valid and latency are
printed. Raw model output is never printed, stored, or transmitted.

Example (local Ollama):
  ollama pull llama3.1
  python scripts/live_probe.py

Example (OpenAI):
  SEISMOGRAPH_PROBE_BASE_URL=https://api.openai.com/v1 \
  SEISMOGRAPH_PROBE_API_KEY=sk-... \
  SEISMOGRAPH_PROBE_MODEL_TUPLE=openai/gpt-4o-mini@2025 \
  python scripts/live_probe.py
"""

from __future__ import annotations

import os
import sys

# Make the repository root importable when this file is run directly
# as a script (``python scripts/live_probe.py``). Run that way,
# sys.path[0] is the script's own directory (scripts/), not the repo
# root, so a bare ``import probe`` fails. Inserting the repo root fixes
# the documented invocation without requiring the caller to set
# PYTHONPATH.
# #SG-TRACE: REQ-CANARY-024
# #   | assumption: the repo root is the parent directory of scripts/
# #   | test: tests/test_providers.py offline import + manual live run
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from probe.canary import execute_canary  # noqa: E402
from probe.providers import (  # noqa: E402
    OpenAICompatibleProvider,
    ProviderError,
)


def main() -> int:
    base_url = os.environ.get(
        "SEISMOGRAPH_PROBE_BASE_URL", "http://localhost:11434/v1"
    )
    api_key = os.environ.get("SEISMOGRAPH_PROBE_API_KEY") or None
    model_tuple = os.environ.get(
        "SEISMOGRAPH_PROBE_MODEL_TUPLE", "ollama/llama3.1"
    )
    max_tokens = int(os.environ.get("SEISMOGRAPH_PROBE_MAX_TOKENS", "64"))

    print(f"Probing {model_tuple} via {base_url} ...\n")
    try:
        provider = OpenAICompatibleProvider(
            base_url=base_url, api_key=api_key, max_tokens=max_tokens
        )
        results = execute_canary(model_tuple, mock=False, provider=provider)
    except ProviderError as exc:
        print(f"Provider call failed: {exc}", file=sys.stderr)
        print(
            "Hint: is the endpoint reachable? For local Ollama run "
            "`ollama serve` and `ollama pull <model>`.",
            file=sys.stderr,
        )
        return 1

    header = f"{'prompt_id':<18}{'hash[:12]':<14}{'len':>5}  "
    header += f"{'json':>5}  {'ms':>6}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.prompt_id:<18}{r.response_hash[:12]:<14}"
            f"{r.output_length:>5}  {str(r.json_valid):>5}  "
            f"{r.latency_ms:>6}"
        )

    print(
        "\nPrivacy check: no raw output above -- only hash, length, "
        "json_valid, latency. Run this on two different model versions "
        "to see the hash/length move: that is drift."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
