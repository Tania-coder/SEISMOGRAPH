"""
COMPARE-1 step 0 -- temperature preflight.

One real call per model at temperature=0. Prints only: HTTP status,
the model name the API returned, finish_reason, the type of content and
its length. Never prints answer text. If a model answers 400, retries
ONCE without temperature and reports whether that succeeded
(contract COMPARE-1 section 6).

Usage (PowerShell, one line):
  python scripts/compare_preflight.py --base-url URL --key-env SG_KEY
      --models model-a model-b

#SG-TRACE: REQ-COMPARE-006
#   | assumption: [assumed, S059] newer models may reject temperature=0
#     with 400; this script turns that into a measurement
#   | test: manual preflight, output pasted into the S060 log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

PROMPT = "Reply with the single word OK."


def _post(url: str, key: str, payload: dict) -> tuple[int, dict | str]:
    """POST JSON; return (status, decoded body or short error text)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        return exc.code, body.replace(key, "<KEY>")
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, f"unreachable: {type(exc).__name__}"


def _summary(status: int, body: dict | str) -> str:
    """One line describing the response, without its text."""
    if not isinstance(body, dict):
        return f"HTTP {status} | error: {body}"
    try:
        choice = body["choices"][0]
        content = choice["message"].get("content")
    except (KeyError, IndexError, TypeError):
        return f"HTTP {status} | unexpected schema"
    kind = type(content).__name__
    size = len(content) if isinstance(content, str) else "-"
    return (
        f"HTTP {status} | returned model={body.get('model')!r} | "
        f"finish_reason={choice.get('finish_reason')!r} | "
        f"content={kind} len={size}"
    )


def check(base_url: str, key: str, model: str) -> None:
    """Call one model at temperature=0, retry once without on 400."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    status, body = _post(url, key, payload)
    print(f"[{model}] temperature=0 -> {_summary(status, body)}")
    if status == 400:
        del payload["temperature"]
        time.sleep(1)
        status, body = _post(url, key, payload)
        print(f"[{model}] no temperature -> {_summary(status, body)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-env", required=True)
    parser.add_argument("--models", nargs="+", required=True)
    args = parser.parse_args()
    key = os.environ.get(args.key_env, "")
    if not key:
        print(f"environment variable {args.key_env} is empty")
        return 2
    for model in args.models:
        check(args.base_url, key, model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
