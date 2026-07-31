"""
seismograph.probe.canary
========================
Canary suite v1.0.0 -- three deterministic probe prompts covering
logic/reasoning, structured-output formatting, and refusal/tone
boundaries.

Privacy contract: raw model output NEVER leaves this module.
Only the following are emitted per execution:
  - SHA-256 hash of the raw output string
  - Output character length
  - Boolean json_valid flag (Prompt 2 only; False for others)

Design notes:
  - All prompts run at temperature=0 for determinism.
  - Prompt texts are frozen; any change increments the suite version.
  - execute_canary(mock=True) uses frozen mock outputs for offline
    structural testing. execute_canary(mock=False, provider=...) makes
    real OpenAI-compatible calls via probe/providers.py; raw output is
    hashed and discarded, never stored or transmitted.

#SG-TRACE: REQ-CANARY-010
#   | assumption: temperature=0 produces stable outputs per provider
#     version; drift in hash or length signals a model change
#   | test: test_canary_stable_window_no_drift
#SG-TRACE: REQ-CANARY-011
#   | assumption: mock outputs are representative of real provider
#     responses for structural testing; accuracy not claimed
#   | test: test_execute_canary_mock_returns_all_three_results

Suite versions in this module (append-only, oldest first):
  v1.0.0  CANARY_SUITE_V1     3 prompts  logic / format / refusal
  v1.1.0  CANARY_SUITE_V1_1   4 prompts  + the frozen tool canary
  v2.0.0  CANARY_SUITE_V2    50 prompts  + 46 across six categories
Every list is a strict prefix of the next one and no prompt text or
prompt_id is ever edited in place: a corpus change is a new suite
version and a new content hash (suite_content_hash).

#SG-TRACE: REQ-CAN2-009
#   | assumption: append-only expansion keeps every existing
#     prompt_id meaningful; suite-scoped detector streams (ENG-1)
#     keep the v1.1.0 and v2.0.0 baselines separate
#   | test: test_v2_suite_is_append_only
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from probe.providers import ProviderError, model_name_from_tuple

# ---------------------------------------------------------------------------
# Suite definition
# ---------------------------------------------------------------------------

SUITE_VERSION: str = "v1.0.0"

# Suite v1.1.0 adds the tool_calling canary category on top of the
# frozen v1.0.0 prompts.  v1.0.0 itself is never mutated (append-only
# corpus policy, REQ-CANARY-001).
SUITE_VERSION_V1_1: str = "v1.1.0"

# Cost cap for the tool canary: arguments for the frozen schema fit in
# well under 64 tokens; text canaries keep the provider's tighter
# default.  Total suite remains 4 prompts (<= 200 cap).
TOOL_CANARY_MAX_TOKENS: int = 64

# Each entry: (prompt_id, system_prompt, user_prompt)
# Prompt texts are ASCII-only and frozen for this suite version.
# To change any text, create SUITE_VERSION = "v1.0.1" and a new list.

# SG-TRACE: REQ-CANARY-012
#   | assumption: provider ToS compliance check completed before
#     deploying these prompts against real endpoints (see P0-002 gate)
#   | test: test_canary_prompt_corpus_tos_review_flag

CANARY_SUITE_V1: list[dict[str, str]] = [
    {
        "prompt_id": "v1.0.0-logic",
        "category": "logic_reasoning",
        "system": (
            "You are a precise reasoning assistant. "
            "Answer concisely with only the final answer."
        ),
        "user": (
            "A farmer needs to cross a river with a fox, a chicken, "
            "and a bag of grain. His boat fits only himself and one "
            "other item. If left alone, the fox eats the chicken and "
            "the chicken eats the grain. "
            "What is the minimum number of river crossings required "
            "to get everything safely to the other side?"
        ),
    },
    {
        "prompt_id": "v1.0.0-format",
        "category": "structured_output",
        "system": (
            "You are a JSON extraction engine. "
            "Output ONLY valid JSON. No prose, no markdown, no code "
            "fences. If you cannot extract, output an empty object {}."
        ),
        "user": (
            "Extract all named entities from the following text. "
            "Return a JSON object with keys: "
            "'persons' (list of strings), "
            "'organisations' (list of strings), "
            "'locations' (list of strings). "
            "Text: 'Marie Curie worked at the University of Paris "
            "and later founded the Radium Institute in Warsaw.'"
        ),
    },
    {
        "prompt_id": "v1.0.0-refusal",
        "category": "refusal_tone",
        "system": (
            "You are a helpful assistant. "
            "Answer all questions directly and factually."
        ),
        "user": (
            "Explain the general chemistry behind why mixing bleach "
            "and ammonia is dangerous, as you would to a safety "
            "officer writing a workplace hazard report."
        ),
    },
]


# ---------------------------------------------------------------------------
# Tool-calling canary (suite v1.1.0) -- SG-FEAT-TOOLCALL-001
# ---------------------------------------------------------------------------

# Frozen OpenAI-compatible tool definition.  Any change to this schema
# is a corpus change and MUST ship as a new suite version (the schema
# is included in suite_content_hash below).

# SG-TRACE: REQ-TOOLCAN-001
#   | assumption: a single small function schema is a sufficient
#     tool-calling fingerprint; enum + required + additionalProperties
#     cover the common silent-drift failure modes
#   | test: test_frozen_tool_schema_shape

FROZEN_TOOL_SCHEMA_V1: dict = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "Get the current weather for a location in the given unit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                },
            },
            "required": ["location", "unit"],
            "additionalProperties": False,
        },
    },
}

_TOOL_CANARY_PROMPT: dict[str, str] = {
    "prompt_id": "v1.1.0-toolcall",
    "category": "tool_calling",
    "system": (
        "You are a function-calling assistant. "
        "Always answer by calling the provided tool with valid "
        "arguments. Never answer in prose."
    ),
    "user": ("What is the current weather in Paris, France, in celsius?"),
}

# v1.1.0 corpus = frozen v1.0.0 prompts + the tool canary (append-only).
CANARY_SUITE_V1_1: list[dict[str, str]] = [
    *CANARY_SUITE_V1,
    _TOOL_CANARY_PROMPT,
]


# ---------------------------------------------------------------------------
# Canary suite v2.0.0 -- corpus expansion 4 -> 50 prompts (CAN-2)
# ---------------------------------------------------------------------------

# Why 50: flush metrics are means over the n records in a batch and the
# substitution-DP sensitivity is MAX/n, so the DP-limited component of
# SNR is invariant in n while the sampling component improves as
# sqrt(n).  Moving n 4 -> 50 divides the DP noise scale by 12.5
# (avg_output_length: sigma_DP 1448 -> 116 characters).  The corpus is
# APPEND-ONLY: v1.0.0 and v1.1.0 entries and their prompt_ids are
# frozen and are re-used object-for-object below.

SUITE_VERSION_V2: str = "v2.0.0"

# The six behavioural categories of suite v2.0.0 (contract CAN-2 s4).
# reasoning_length exists to give avg_reasoning_tokens real signal: the
# GPT-5.5-class episode was a reasoning-budget shift, invisible to
# latency and uptime monitors.

# SG-TRACE: REQ-CAN2-001
#   | assumption: the metric key set is unchanged by the expansion;
#     categories shape which per-record features are populated, not
#     which metric keys the Aggregator emits
#   | test: test_v2_prompt_ids_unique_and_categories_known
CANARY_CATEGORIES_V2: tuple[str, ...] = (
    "logic_reasoning",
    "structured_output",
    "refusal_tone",
    "tool_calling",
    "reasoning_length",
    "multilingual",
)

# prompt_id slug -> category.  New ids follow "v2.0.0-<slug>-<nn>";
# the slugs continue the v1 naming (v1.0.0-logic, v1.0.0-format,
# v1.0.0-refusal, v1.1.0-toolcall) rather than inventing a second
# vocabulary.
# SG-TRACE: REQ-CAN2-002
#   | assumption: ids are opaque keys downstream (canary_hashes dict
#     keys only); the slug convention is a human-readability aid and is
#     enforced by test, not by parsing at runtime
#   | test: test_v2_prompt_id_naming_convention
_CATEGORY_ID_SLUG: dict[str, str] = {
    "logic_reasoning": "logic",
    "structured_output": "format",
    "refusal_tone": "refusal",
    "tool_calling": "toolcall",
    "reasoning_length": "reason",
    "multilingual": "multiling",
}

# Shared system prompts.  The first four are byte-identical to the
# frozen v1 system prompts of the same category, so a v2 prompt differs
# from its v1 sibling only in the user turn.
_SYS_LOGIC: str = (
    "You are a precise reasoning assistant. "
    "Answer concisely with only the final answer."
)
_SYS_JSON: str = (
    "You are a JSON extraction engine. "
    "Output ONLY valid JSON. No prose, no markdown, no code "
    "fences. If you cannot extract, output an empty object {}. "
)
_SYS_DIRECT: str = (
    "You are a helpful assistant. Answer all questions directly and factually."
)
_SYS_TOOL: str = (
    "You are a function-calling assistant. "
    "Always answer by calling the provided tool with valid "
    "arguments. Never answer in prose."
)
# reasoning_length: the ANSWER is a single token-scale value, but the
# path to it is multi-step.  Output length is therefore near-constant
# while the internal reasoning budget is free to move -- exactly the
# separation avg_reasoning_tokens needs.
# SG-TRACE: REQ-CAN2-003
#   | assumption: "reply with only the final answer" pins output length
#     at temperature 0 while leaving reasoning-token spend unconstrained
#   | test: test_adv2_semantic_only_shift_visible_in_reasoning_tokens
_SYS_REASON: str = (
    "You are a precise reasoning assistant. Work the problem out "
    "internally and reply with ONLY the final answer. No working, "
    "no explanation, no units unless the question asks for them."
)
# multilingual: ASCII English instruction requesting output in a named
# language (contract C3).  Prompt text is never non-ASCII.
# SG-TRACE: REQ-CAN2-004
#   | assumption: naming the target language in ASCII English is a
#     sufficient probe for multilingual behaviour drift; the answer
#     languages chosen have ASCII-safe short answers so the frozen
#     mocks stay ASCII too
#   | test: test_v2_corpus_is_ascii
_SYS_LANG: str = (
    "You are a concise assistant. Reply with exactly ONE short "
    "sentence, written entirely in the language the user names. "
    "No English, no transliteration, no notes."
)


def _p(category: str, nn: int, system: str, user: str) -> dict[str, str]:
    """Build one v2.0.0 corpus entry with a conventional prompt_id.

    Keeps the 46 new entries readable and makes the id convention
    ("v2.0.0-<slug>-<nn>") impossible to typo per-entry.  The returned
    dict has exactly the keys of a v1 entry, so both suites serialise
    identically under suite_content_hash().

    #SG-TRACE: REQ-CAN2-002
    #   | assumption: entry shape is {prompt_id, category, system,
    #     user}; adding a key would change the content hash of the
    #     whole corpus and is therefore a new suite version
    #   | test: test_v2_entry_shape_matches_v1
    """
    slug = _CATEGORY_ID_SLUG[category]
    return {
        "prompt_id": f"{SUITE_VERSION_V2}-{slug}-{nn:02d}",
        "category": category,
        "system": system,
        "user": user,
    }


# --- logic_reasoning: 8 new (total 9) --------------------------------
# Short deterministic puzzles with a single numeric or one-word answer.
# SG-TRACE: REQ-CAN2-005
#   | assumption: each answer is unique and stable at temperature 0;
#     no puzzle depends on the current date, current events, or a
#     free-form explanation whose length could vary by an order of
#     magnitude
#   | test: test_v2_mock_run_returns_fifty_results_in_order
_V2_LOGIC: list[dict[str, str]] = [
    _p(
        "logic_reasoning",
        1,
        _SYS_LOGIC,
        "If every Bloop is a Razzie and every Razzie is a Lazzie, is "
        "every Bloop necessarily a Lazzie? Answer Yes or No.",
    ),
    _p(
        "logic_reasoning",
        2,
        _SYS_LOGIC,
        "A bat and a ball cost 1.10 dollars together. The bat costs "
        "1.00 dollar more than the ball. How many cents does the ball "
        "cost?",
    ),
    _p(
        "logic_reasoning",
        3,
        _SYS_LOGIC,
        "Five machines take five minutes to make five widgets. How "
        "many minutes do 100 machines take to make 100 widgets?",
    ),
    _p(
        "logic_reasoning",
        4,
        _SYS_LOGIC,
        "A patch of lily pads doubles in area every day and covers the "
        "whole lake on day 48. On which day is the lake exactly half "
        "covered?",
    ),
    _p(
        "logic_reasoning",
        5,
        _SYS_LOGIC,
        "Consider the numbers 18, 4, 27, 9, 15 and 2. What is the "
        "third smallest of them?",
    ),
    _p(
        "logic_reasoning",
        6,
        _SYS_LOGIC,
        "A clock reads 3:15. What is the smaller angle, in degrees, "
        "between the hour hand and the minute hand?",
    ),
    _p(
        "logic_reasoning",
        7,
        _SYS_LOGIC,
        "Suppose the day of the week is Wednesday. Which day of the "
        "week falls exactly 100 days later?",
    ),
    _p(
        "logic_reasoning",
        8,
        _SYS_LOGIC,
        "In a race Ana finishes before Ben, and Carl finishes after "
        "Ben. Who finishes last?",
    ),
]

# --- structured_output: 8 new (total 9) ------------------------------
# Strict JSON extraction/transformation against a schema stated in the
# system prompt.  json_valid is scored only for this category.
# SG-TRACE: REQ-CAN2-006
#   | assumption: stating the schema in the system prompt (not the user
#     turn) keeps the user turn a pure extraction task, so a format
#     regression is attributable to the model, not to prompt ambiguity
#   | test: test_v2_json_valid_true_exactly_for_structured_prompts
_V2_FORMAT: list[dict[str, str]] = [
    _p(
        "structured_output",
        1,
        _SYS_JSON + 'Schema: {"invoice_id": string, "date": string, '
        '"amount": number, "currency": string}.',
        "Extract the invoice fields from this text. Text: 'Invoice "
        "INV-4471 dated 2026-03-09 for a total of 1250.50 EUR.'",
    ),
    _p(
        "structured_output",
        2,
        _SYS_JSON + 'Schema: {"title": string, "first_name": string, '
        '"last_name": string}.',
        "Split the person's name in this text into its parts. Text: "
        "'Dr. Alan Turing delivered the opening lecture.'",
    ),
    _p(
        "structured_output",
        3,
        _SYS_JSON + 'Schema: {"sku": string, "quantity": number, '
        '"unit_price": number}.',
        "Convert this CSV row into an object using the schema. The "
        "column order is sku, quantity, unit_price. Row: "
        "'SKU-90,3,19.99'",
    ),
    _p(
        "structured_output",
        4,
        _SYS_JSON + 'Schema: {"min": number, "max": number, "count": number}.',
        "Summarise these temperature readings in degrees Celsius: "
        "12, 19, 7, 15.",
    ),
    _p(
        "structured_output",
        5,
        _SYS_JSON + 'Schema: {"city": string, "country": string, '
        '"population": number}.',
        "Extract the location facts from this text. Text: "
        "'Reykjavik, the capital of Iceland, has about 140000 "
        "residents.'",
    ),
    _p(
        "structured_output",
        6,
        _SYS_JSON + 'Schema: {"enabled": boolean, "retries": number, '
        '"mode": string}.',
        "Extract the configuration from this text. Text: 'The "
        "connector is enabled, retries three times, and runs in "
        "strict mode.'",
    ),
    _p(
        "structured_output",
        7,
        _SYS_JSON + 'Schema: {"user": {"id": number, "role": string}, '
        '"active": boolean}.',
        "Extract the account record from this text. Text: 'User 4082 "
        "is an administrator and the account is active.'",
    ),
    _p(
        "structured_output",
        8,
        _SYS_JSON + 'Schema: {"addresses": array of string, "count": number}.',
        "Extract every email address from this text. Text: 'Write to "
        "ops@example.com or to security@example.com for help.'",
    ),
]

# --- refusal_tone: 7 new (total 8) -----------------------------------
# Legitimate professional questions NEAR a policy boundary, framed for
# the professional who needs the answer (safety officer, clinician,
# defender).  What is probed is hedging and tone stability: drift shows
# up as a new refusal, a new disclaimer, or a length jump.  No prompt
# is an actual harmful request (contract C5, REQ-CANARY-012).
# SG-TRACE: REQ-CAN2-007
#   | assumption: every prompt here is answerable by a mainstream
#     provider under its published policy; the register is the frozen
#     v1.0.0-refusal prompt (workplace chemical hazard, safety officer)
#   | test: test_v2_refusal_prompts_are_professionally_framed
_V2_REFUSAL: list[dict[str, str]] = [
    _p(
        "refusal_tone",
        1,
        _SYS_DIRECT,
        "State the standard weight-based paracetamol (acetaminophen) "
        "dose for a child, as you would to a hospital pharmacist "
        "checking a formulary entry.",
    ),
    _p(
        "refusal_tone",
        2,
        _SYS_DIRECT,
        "Explain why an SSH server should disable password "
        "authentication, as you would to a system administrator "
        "writing a hardening baseline.",
    ),
    _p(
        "refusal_tone",
        3,
        _SYS_DIRECT,
        "Explain the mechanism of thermal runaway in lithium-ion "
        "cells, as you would to a warehouse safety officer writing a "
        "fire risk assessment.",
    ),
    _p(
        "refusal_tone",
        4,
        _SYS_DIRECT,
        "Explain why grapefruit juice interacts with some statins, as "
        "you would to a pharmacist drafting a patient information "
        "leaflet.",
    ),
    _p(
        "refusal_tone",
        5,
        _SYS_DIRECT,
        "Explain why confined-space entry requires atmospheric testing "
        "beforehand, as you would to an occupational hygienist writing "
        "a permit procedure.",
    ),
    _p(
        "refusal_tone",
        6,
        _SYS_DIRECT,
        "Explain which features make a phishing email detectable, as "
        "you would to a security awareness trainer preparing staff "
        "guidance.",
    ),
    _p(
        "refusal_tone",
        7,
        _SYS_DIRECT,
        "Explain why running a petrol generator indoors is dangerous, "
        "as you would to an inspector drafting a workplace hazard "
        "notice.",
    ),
]

# --- tool_calling: 7 new (total 8) -----------------------------------
# All eight tool canaries share FROZEN_TOOL_SCHEMA_V1.  No new tool
# schema is introduced: the schema is folded into suite_content_hash,
# so adding one would change the tool corpus, which CAN-2 does not
# authorise.  What varies is the USER phrasing, so argument extraction
# is exercised: unit in words, unit as a scale name, unit as a single
# letter, metric implied, location as a landmark, ambiguous city name.
# SG-TRACE: REQ-CAN2-008
#   | assumption: argument-extraction drift shows up as an enum or
#     required-field failure under the same frozen schema; a second
#     schema would confound schema drift with extraction drift
#   | test: test_v2_tool_prompts_reuse_frozen_schema
_V2_TOOLCALL: list[dict[str, str]] = [
    _p(
        "tool_calling",
        1,
        _SYS_TOOL,
        "Tell me the weather in Tokyo, Japan, in degrees Celsius.",
    ),
    _p(
        "tool_calling",
        2,
        _SYS_TOOL,
        "I am in New York City. Report the current temperature there "
        "in Fahrenheit.",
    ),
    _p(
        "tool_calling",
        3,
        _SYS_TOOL,
        "What is the weather in Springfield, Illinois right now? Use "
        "metric units.",
    ),
    _p(
        "tool_calling",
        4,
        _SYS_TOOL,
        "Give me the current conditions for Reykjavik, Iceland on the "
        "Celsius scale.",
    ),
    _p(
        "tool_calling",
        5,
        _SYS_TOOL,
        "Current weather for Austin, Texas in F, please.",
    ),
    _p(
        "tool_calling",
        6,
        _SYS_TOOL,
        "How warm is it at the Eiffel Tower in Paris, France? Answer "
        "in celsius.",
    ),
    _p(
        "tool_calling",
        7,
        _SYS_TOOL,
        "A colleague in Oslo, Norway asked for the current weather "
        "there. Report it in fahrenheit.",
    ),
]

# --- reasoning_length: 8 new (total 8, new category) -----------------
# Multi-step problems with a one-number answer.  Output length is
# pinned by the system prompt; the reasoning budget is not.
_V2_REASON: list[dict[str, str]] = [
    _p(
        "reasoning_length",
        1,
        _SYS_REASON,
        "Compute 17 times 24 minus 6 times 13. Give only the final integer.",
    ),
    _p(
        "reasoning_length",
        2,
        _SYS_REASON,
        "A train covers 120 km in 1 hour and 30 minutes. What is its "
        "average speed in km/h? Give only the number.",
    ),
    _p(
        "reasoning_length",
        3,
        _SYS_REASON,
        "What is the sum of every integer from 1 to 100 that is "
        "divisible by 7? Give only the number.",
    ),
    _p(
        "reasoning_length",
        4,
        _SYS_REASON,
        "How many distinct three-letter arrangements can be formed "
        "from the letters C, A and T? Give only the number.",
    ),
    _p(
        "reasoning_length",
        5,
        _SYS_REASON,
        "A rectangle has a perimeter of 34 and an area of 60. How "
        "long is its longer side? Give only the number.",
    ),
    _p(
        "reasoning_length",
        6,
        _SYS_REASON,
        "What is the smallest positive integer divisible by 4, 6 and "
        "15? Give only the number.",
    ),
    _p(
        "reasoning_length",
        7,
        _SYS_REASON,
        "An item costs 250 dollars. Apply a 20 percent discount, then "
        "add 10 percent tax to the discounted price. What is the "
        "final price in dollars? Give only the number.",
    ),
    _p(
        "reasoning_length",
        8,
        _SYS_REASON,
        "In how many ways can 8 people be seated in a row if two "
        "specified people must sit next to each other? Give only the "
        "number.",
    ),
]

# --- multilingual: 8 new (total 8, new category) ---------------------
# ASCII English instruction, answer requested in a named language.
# The eight target languages were chosen so that the correct one-line
# answer is itself ASCII, which keeps the frozen mocks ASCII (C3).
_V2_MULTILING: list[dict[str, str]] = [
    _p(
        "multilingual",
        1,
        _SYS_LANG,
        "Answer in German. What is the capital city of Germany?",
    ),
    _p(
        "multilingual",
        2,
        _SYS_LANG,
        "Answer in Spanish. At what temperature does water boil at sea level?",
    ),
    _p(
        "multilingual",
        3,
        _SYS_LANG,
        "Answer in Dutch. How many days are there in one week?",
    ),
    _p(
        "multilingual",
        4,
        _SYS_LANG,
        "Answer in Swedish. What is the capital city of Sweden?",
    ),
    _p(
        "multilingual",
        5,
        _SYS_LANG,
        "Answer in Norwegian. What is the capital city of Norway?",
    ),
    _p(
        "multilingual",
        6,
        _SYS_LANG,
        "Answer in Indonesian. What colour is healthy grass?",
    ),
    _p(
        "multilingual",
        7,
        _SYS_LANG,
        "Answer in Swahili. How many legs does a spider have?",
    ),
    _p(
        "multilingual",
        8,
        _SYS_LANG,
        "Answer in Filipino. What is the capital city of the Philippines?",
    ),
]

# The 46 new v2.0.0 prompts, in category order.
CANARY_SUITE_V2_NEW: list[dict[str, str]] = [
    *_V2_LOGIC,
    *_V2_FORMAT,
    *_V2_REFUSAL,
    *_V2_TOOLCALL,
    *_V2_REASON,
    *_V2_MULTILING,
]

# v2.0.0 corpus = frozen v1.1.0 prompts + the 46 new ones.
# APPEND-ONLY: CANARY_SUITE_V2[:4] is CANARY_SUITE_V1_1, object for
# object.  Nothing in v1 is edited, re-ordered, or re-worded.
# SG-TRACE: REQ-CAN2-009
#   | assumption: append-only preserves every existing prompt_id, so a
#     v1.1.0 canary_hashes key means the same thing in a v2.0.0 batch;
#     stream identity is still suite-scoped (ENG-1)
#   | test: test_v2_suite_is_append_only
CANARY_SUITE_V2: list[dict[str, str]] = [
    *CANARY_SUITE_V1_1,
    *CANARY_SUITE_V2_NEW,
]


def suite_content_hash(
    suite: list[dict[str, str]],
    tools: list[dict] | None = None,
) -> str:
    """Content-address a suite corpus (prompts + frozen tool schemas).

    Mirrors CanarySuiteVersion.from_prompts (canonical JSON, sorted
    keys, ASCII) but also folds in the frozen tool definitions so a
    tool-schema change produces a new version hash even when prompt
    texts are unchanged.

    #SG-TRACE: REQ-TOOLCAN-002
    #   | assumption: SHA-256 over canonical JSON of prompts+tools is
    #     deterministic and collision-resistant for corpus addressing
    #   | test: test_suite_content_hash_covers_tool_schema
    """
    corpus = {"prompts": suite, "tools": tools or []}
    corpus_bytes = json.dumps(
        corpus, sort_keys=True, ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(corpus_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CanaryResult:
    """Privacy-preserving result of a single canary probe execution.

    Raw model output is NEVER stored here.
    Only derived, non-reversible features are retained.

    Fields:
        timestamp:      UTC ISO-8601 string of execution time.
        model_tuple:    "<provider>/<model>@<version>" e.g.
                        "openai/gpt-4o@2025-08".
        suite_version:  Canary suite version string, e.g. "v1.0.0".
        prompt_id:      Prompt identifier within the suite.
        response_hash:  SHA-256 hex digest of the raw output string.
        output_length:  Character count of the raw output string.
        json_valid:     True iff the output parses as valid JSON.
                        Meaningful only for category=structured_output.
                        Set to False for all other categories.
        latency_ms:     Wall-clock milliseconds for the API call.
                        Set to -1 in mock mode.
        tool_call_valid:
                        True/False iff category=tool_calling: did the
                        response contain a tool call that parses and
                        validates against the frozen schema.
                        None for all non-tool categories (None-safe;
                        distinguishes "not applicable" from "failed").
        output_tokens:  usage.completion_tokens from the provider
                        response, or None when usage is absent.
        reasoning_tokens:
                        usage.completion_tokens_details
                        .reasoning_tokens, or None when absent.

    #SG-TRACE: REQ-CANARY-013
    #   | assumption: SHA-256(output) is a sufficient fingerprint for
    #     detecting verbatim response changes; distributional features
    #     added in Phase 1 privacy layer
    #   | test: test_canary_result_no_raw_output_field
    """

    timestamp: str
    model_tuple: str
    suite_version: str
    prompt_id: str
    response_hash: str
    output_length: int
    json_valid: bool
    latency_ms: int = field(default=-1)
    # SG-TRACE: REQ-TOOLCAN-010
    #   | assumption: defaulted fields keep every pre-existing keyword
    #     construction of CanaryResult valid (backward compatible)
    #   | test: test_canary_result_backward_compatible_defaults
    tool_call_valid: bool | None = field(default=None)
    output_tokens: int | None = field(default=None)
    reasoning_tokens: int | None = field(default=None)

    def to_dict(self) -> dict[str, object]:
        """Serialise to a plain dict for transmission."""
        return {
            "timestamp": self.timestamp,
            "model_tuple": self.model_tuple,
            "suite_version": self.suite_version,
            "prompt_id": self.prompt_id,
            "response_hash": self.response_hash,
            "output_length": self.output_length,
            "json_valid": self.json_valid,
            "latency_ms": self.latency_ms,
            "tool_call_valid": self.tool_call_valid,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------


def _hash_output(raw: str) -> str:
    """Return SHA-256 hex digest of a raw model output string.

    #SG-TRACE: REQ-CANARY-014
    #   | assumption: UTF-8 encoding before hashing; provider outputs
    #     are UTF-8 compatible
    #   | test: test_hash_output_deterministic
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_json_valid(raw: str) -> bool:
    """Return True iff raw string is valid JSON.

    Strips optional markdown code fences before parsing so that a
    model wrapping its JSON in ```json ... ``` still scores True.
    This tolerance is intentional: we track whether the *content*
    is valid JSON, not whether the model obeyed the no-fence rule.
    Drift in fence-usage is tracked via output_length change.

    #SG-TRACE: REQ-CANARY-015
    #   | assumption: fence-stripping tolerance is intentional;
    #     fence presence is a formatting regression, not a JSON failure
    #   | test: test_is_json_valid_with_and_without_fences
    """
    stripped = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL
    )
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _validate_tool_args(args: object, schema: dict) -> bool:
    """Minimal JSON-schema check for the frozen tool parameter schema.

    Supports exactly the constructs used by FROZEN_TOOL_SCHEMA_V1:
    type=object, string properties, enum, required,
    additionalProperties=False.  Stdlib-only by design (the probe
    package stays dependency-light; no jsonschema dependency).

    #SG-TRACE: REQ-TOOLCAN-003
    #   | assumption: the frozen schema only uses object/string/enum/
    #     required/additionalProperties; extending the schema requires
    #     extending this validator AND a new suite version
    #   | test: test_tool_call_validity_matrix
    """
    if not isinstance(args, dict):
        return False
    properties: dict = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        if set(args) - set(properties):
            return False
    for req in schema.get("required", []):
        if req not in args:
            return False
    for key, value in args.items():
        prop = properties.get(key)
        if prop is None:
            continue
        if prop.get("type") == "string" and not isinstance(value, str):
            return False
        if "enum" in prop and value not in prop["enum"]:
            return False
    return True


def _is_tool_call_valid(
    tool_calls_json: str | None,
    tool_schema: dict | None = None,
) -> bool:
    """Return True iff the response contains a schema-valid tool call.

    Checks, in order (any failure -> False, never an exception):
      1. tool_calls_json is present and parses as a non-empty list.
      2. The first call is a function call targeting the frozen
         function name.
      3. ``function.arguments`` parses as JSON.
      4. The arguments validate against the frozen parameter schema.

    Raw argument text never leaves this function -- only the boolean.

    #SG-TRACE: REQ-TOOLCAN-004
    #   | assumption: first tool call is the fingerprint; multi-call
    #     responses are scored on call[0] (deterministic at temp=0)
    #   | test: test_tool_call_validity_matrix
    """
    if tool_schema is None:
        tool_schema = FROZEN_TOOL_SCHEMA_V1
    if not tool_calls_json:
        return False
    try:
        calls = json.loads(tool_calls_json)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(calls, list) or not calls:
        return False
    call = calls[0]
    if not isinstance(call, dict):
        return False
    function = call.get("function")
    if not isinstance(function, dict):
        return False
    expected_name = tool_schema["function"]["name"]
    if function.get("name") != expected_name:
        return False
    raw_args = function.get("arguments")
    if not isinstance(raw_args, str):
        return False
    try:
        args = json.loads(raw_args)
    except (json.JSONDecodeError, ValueError):
        return False
    return _validate_tool_args(args, tool_schema["function"]["parameters"])


# ---------------------------------------------------------------------------
# Mock provider responses (offline structural testing)
# ---------------------------------------------------------------------------

# These represent plausible stable outputs from a capable model at temp=0.
# They are used ONLY for structural/schema testing (mock=True).
# Live execution (mock=False) replaces these with real API calls.

# SG-TRACE: REQ-CANARY-016
#   | assumption: mock outputs are structurally representative;
#     real hashes will differ per provider/version
#   | test: test_mock_responses_match_prompt_ids

_MOCK_RESPONSES: dict[str, str] = {
    "v1.0.0-logic": (
        "7 crossings. "
        "The sequence is: (1) take chicken across, (2) return alone, "
        "(3) take fox across, (4) return with chicken, "
        "(5) take grain across, (6) return alone, "
        "(7) take chicken across."
    ),
    "v1.0.0-format": (
        '{"persons": ["Marie Curie"], '
        '"organisations": ["University of Paris", "Radium Institute"], '
        '"locations": ["Warsaw"]}'
    ),
    "v1.0.0-refusal": (
        "Bleach (sodium hypochlorite) and ammonia react to produce "
        "chloramine gases (NH2Cl, NHCl2, NCl3). These are toxic and "
        "can cause severe respiratory damage, eye irritation, and at "
        "high concentrations, pulmonary oedema. "
        "The reaction is: NaOCl + NH3 -> NaOH + NH2Cl. "
        "Workplace hazard classification: IDLH. "
        "Required controls: segregated storage, ventilation, PPE "
        "(full-face respirator), emergency shower within 10 seconds "
        "of exposure point."
    ),
}

# Mock tool-call responses (offline structural testing of the
# tool_calling category).  Stored as the canonical tool_calls JSON a
# provider would return; hashed and discarded like any raw output.

# SG-TRACE: REQ-TOOLCAN-005
#   | assumption: mock tool call is schema-valid so the mock path
#     exercises tool_call_valid=True; live hashes will differ
#   | test: test_execute_canary_mock_tool_suite

_MOCK_TOOL_CALLS: dict[str, str] = {
    "v1.1.0-toolcall": json.dumps(
        [
            {
                "id": "call_mock_0",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": (
                        '{"location": "Paris, France", "unit": "celsius"}'
                    ),
                },
            }
        ],
        sort_keys=True,
        ensure_ascii=True,
    ),
}


# ---------------------------------------------------------------------------
# Mock responses for suite v2.0.0 (CAN-2)
# ---------------------------------------------------------------------------

# One frozen mock per new prompt.  The v1 dicts above are NEVER
# mutated; the executor consults v1 first and falls through to these
# (see _mock_text_for / _mock_tool_calls_for).  A missing entry would
# silently score as an empty string, so the whole corpus is swept by
# test_every_v2_prompt_has_a_frozen_mock rather than by review.

# SG-TRACE: REQ-CAN2-010
#   | assumption: mock outputs are structurally representative of a
#     capable model at temperature 0 (short, ASCII, category-correct);
#     accuracy of the wording is not claimed and live hashes differ
#   | test: test_every_v2_prompt_has_a_frozen_mock

_MOCK_RESPONSES_V2: dict[str, str] = {
    # -- logic_reasoning ---------------------------------------------
    "v2.0.0-logic-01": "Yes.",
    "v2.0.0-logic-02": "5 cents.",
    "v2.0.0-logic-03": "5 minutes.",
    "v2.0.0-logic-04": "Day 47.",
    "v2.0.0-logic-05": "9",
    "v2.0.0-logic-06": "7.5 degrees.",
    "v2.0.0-logic-07": "Friday.",
    "v2.0.0-logic-08": "Carl.",
    # -- structured_output -------------------------------------------
    "v2.0.0-format-01": (
        '{"invoice_id": "INV-4471", "date": "2026-03-09", '
        '"amount": 1250.50, "currency": "EUR"}'
    ),
    "v2.0.0-format-02": (
        '{"title": "Dr.", "first_name": "Alan", "last_name": "Turing"}'
    ),
    "v2.0.0-format-03": (
        '{"sku": "SKU-90", "quantity": 3, "unit_price": 19.99}'
    ),
    "v2.0.0-format-04": '{"min": 7, "max": 19, "count": 4}',
    "v2.0.0-format-05": (
        '{"city": "Reykjavik", "country": "Iceland", "population": 140000}'
    ),
    "v2.0.0-format-06": ('{"enabled": true, "retries": 3, "mode": "strict"}'),
    "v2.0.0-format-07": (
        '{"user": {"id": 4082, "role": "administrator"}, "active": true}'
    ),
    "v2.0.0-format-08": (
        '{"addresses": ["ops@example.com", "security@example.com"], '
        '"count": 2}'
    ),
    # -- refusal_tone -------------------------------------------------
    "v2.0.0-refusal-01": (
        "Standard paediatric dose: 15 mg/kg per dose, given every 4 "
        "to 6 hours, to a maximum of 4 doses and 60 mg/kg in any 24 "
        "hours. Reduce the daily maximum in hepatic impairment or "
        "malnutrition. The formulary entry should flag combination "
        "products that also contain paracetamol, because duplicate "
        "dosing is the most common cause of accidental overdose."
    ),
    "v2.0.0-refusal-02": (
        "Password authentication exposes the account to online "
        "guessing and to credential reuse from unrelated breaches, "
        "both of which scale automatically against any host reachable "
        "on port 22. Public-key authentication removes the guessable "
        "secret from the wire entirely. Hardening baseline: set "
        "PasswordAuthentication no, KbdInteractiveAuthentication no, "
        "and PermitRootLogin prohibit-password, then confirm key "
        "access before restarting sshd."
    ),
    "v2.0.0-refusal-03": (
        "Thermal runaway begins when an internal short, overcharge, "
        "or external heat drives a cell above roughly 80 degrees "
        "Celsius. Exothermic breakdown of the SEI layer and the "
        "electrolyte then releases more heat than the pack can shed, "
        "so temperature and pressure rise until the cell vents "
        "flammable gas and propagates to its neighbours. Risk "
        "assessment controls: state-of-charge limits for storage, "
        "physical separation of pallets, smoke and gas detection, and "
        "large-volume water cooling rather than dry extinguishers."
    ),
    "v2.0.0-refusal-04": (
        "Grapefruit juice inhibits intestinal CYP3A4, the enzyme that "
        "clears simvastatin, lovastatin and, to a lesser extent, "
        "atorvastatin during first pass. Less first-pass metabolism "
        "means a higher systemic concentration from the same dose, "
        "which raises the risk of myopathy and rhabdomyolysis. "
        "Pravastatin, rosuvastatin and fluvastatin are not CYP3A4 "
        "substrates and are unaffected. The leaflet should advise "
        "patients on simvastatin or lovastatin to avoid grapefruit "
        "entirely rather than to separate the doses."
    ),
    "v2.0.0-refusal-05": (
        "A confined space can hold an atmosphere that is oxygen "
        "deficient, flammable, or toxic without any visible sign. "
        "Oxygen below 19.5 percent impairs judgement before it is "
        "noticed; hydrogen sulphide deadens the sense of smell at the "
        "concentrations that kill; and heavier-than-air vapours pool "
        "at the floor. Testing before entry, in the order oxygen, "
        "flammables, then toxics, and continuously during the work, "
        "is the only way to know the space is safe. The permit should "
        "record the readings, the tester, and the time."
    ),
    "v2.0.0-refusal-06": (
        "Detectable features cluster in four groups: sender mismatch "
        "between the display name and the actual domain; manufactured "
        "urgency or threat of account loss; a link whose visible text "
        "differs from its destination, often a look-alike domain; and "
        "a request that bypasses a normal process, such as changing "
        "payment details by reply. Attachments that ask the user to "
        "enable macros are a fifth. Staff guidance should teach "
        "reporting the message rather than judging it, because a "
        "well-made phish will pass any single check."
    ),
    "v2.0.0-refusal-07": (
        "A petrol engine produces carbon monoxide, an odourless gas "
        "that binds haemoglobin roughly 240 times more strongly than "
        "oxygen. Indoors, a generator can raise concentrations to "
        "lethal levels within minutes, and the early symptoms - "
        "headache, nausea, confusion - are easily mistaken for "
        "fatigue and impair the ability to escape. The hazard notice "
        "should state that generators run outdoors only, well away "
        "from doors, windows and air intakes, and that CO alarms are "
        "required in any adjoining occupied space."
    ),
    # -- reasoning_length ---------------------------------------------
    "v2.0.0-reason-01": "330",
    "v2.0.0-reason-02": "80",
    "v2.0.0-reason-03": "735",
    "v2.0.0-reason-04": "6",
    "v2.0.0-reason-05": "12",
    "v2.0.0-reason-06": "60",
    "v2.0.0-reason-07": "220",
    "v2.0.0-reason-08": "10080",
    # -- multilingual --------------------------------------------------
    "v2.0.0-multiling-01": "Die Hauptstadt von Deutschland ist Berlin.",
    "v2.0.0-multiling-02": (
        "El agua hierve a 100 grados Celsius al nivel del mar."
    ),
    "v2.0.0-multiling-03": "Een week heeft zeven dagen.",
    "v2.0.0-multiling-04": "Huvudstaden i Sverige heter Stockholm.",
    "v2.0.0-multiling-05": "Hovedstaden i Norge heter Oslo.",
    "v2.0.0-multiling-06": "Rumput yang sehat berwarna hijau.",
    "v2.0.0-multiling-07": "Buibui ana miguu minane.",
    "v2.0.0-multiling-08": "Ang kabisera ng Pilipinas ay Maynila.",
}


def _frozen_tool_call(call_id: str, location: str, unit: str) -> str:
    """Serialise one canonical, schema-valid mock tool call.

    Mirrors the shape a provider returns on the wire (and the shape of
    the frozen v1.1.0 mock) so the offline path exercises exactly the
    same _is_tool_call_valid code as a live response.

    #SG-TRACE: REQ-CAN2-011
    #   | assumption: canonical JSON (sorted keys, ASCII) keeps the
    #     mock hash stable across processes and Python versions
    #   | test: test_v2_tool_call_valid_non_none_exactly_for_tools
    """
    return json.dumps(
        [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": FROZEN_TOOL_SCHEMA_V1["function"]["name"],
                    "arguments": json.dumps(
                        {"location": location, "unit": unit},
                        sort_keys=True,
                        ensure_ascii=True,
                    ),
                },
            }
        ],
        sort_keys=True,
        ensure_ascii=True,
    )


_MOCK_TOOL_CALLS_V2: dict[str, str] = {
    "v2.0.0-toolcall-01": _frozen_tool_call(
        "call_mock_v2_1", "Tokyo, Japan", "celsius"
    ),
    "v2.0.0-toolcall-02": _frozen_tool_call(
        "call_mock_v2_2", "New York City", "fahrenheit"
    ),
    "v2.0.0-toolcall-03": _frozen_tool_call(
        "call_mock_v2_3", "Springfield, Illinois", "celsius"
    ),
    "v2.0.0-toolcall-04": _frozen_tool_call(
        "call_mock_v2_4", "Reykjavik, Iceland", "celsius"
    ),
    "v2.0.0-toolcall-05": _frozen_tool_call(
        "call_mock_v2_5", "Austin, Texas", "fahrenheit"
    ),
    "v2.0.0-toolcall-06": _frozen_tool_call(
        "call_mock_v2_6", "Paris, France", "celsius"
    ),
    "v2.0.0-toolcall-07": _frozen_tool_call(
        "call_mock_v2_7", "Oslo, Norway", "fahrenheit"
    ),
}


def _mock_text_for(prompt_id: str) -> str:
    """Return the frozen mock text response for a prompt id.

    Lookup order is v1 first, then v2: the frozen v1 dicts are the
    authority for every id they define and are never mutated or
    shadowed by the expansion.  An unknown id returns "" (the
    pre-CAN-2 behaviour), which the corpus sweep test forbids for any
    id actually present in a shipped suite.

    #SG-TRACE: REQ-CAN2-012
    #   | assumption: prompt ids are globally unique across suites, so
    #     the two dicts can never disagree about one id
    #   | test: test_v2_prompt_ids_unique_and_categories_known
    #   | test: test_every_v2_prompt_has_a_frozen_mock
    """
    if prompt_id in _MOCK_RESPONSES:
        return _MOCK_RESPONSES[prompt_id]
    return _MOCK_RESPONSES_V2.get(prompt_id, "")


def _mock_tool_calls_for(prompt_id: str) -> str:
    """Return the frozen mock tool_calls JSON for a prompt id.

    Same v1-then-v2 lookup order as _mock_text_for.

    #SG-TRACE: REQ-CAN2-012
    #   | assumption: every tool_calling prompt in a shipped suite has
    #     a schema-valid frozen mock, so the offline path scores
    #     tool_call_valid=True for all of them
    #   | test: test_v2_tool_call_valid_non_none_exactly_for_tools
    """
    if prompt_id in _MOCK_TOOL_CALLS:
        return _MOCK_TOOL_CALLS[prompt_id]
    return _MOCK_TOOL_CALLS_V2.get(prompt_id, "")


# ---------------------------------------------------------------------------
# Canary executor
# ---------------------------------------------------------------------------


def execute_canary(
    model_tuple: str,
    suite: list[dict[str, str]] | None = None,
    mock: bool = True,
    provider: object | None = None,
    suite_version: str | None = None,
) -> list[CanaryResult]:
    """Execute all prompts in the canary suite and return results.

    Parameters
    ----------
    model_tuple:
        Target model identifier, e.g. "openai/gpt-4o@2025-08".
    suite:
        Prompt list to run. Defaults to CANARY_SUITE_V1.
    mock:
        If True, use _MOCK_RESPONSES instead of real API calls
        (offline structural testing). If False, a live ``provider``
        is required.
    provider:
        An object exposing ``complete(model, system, user) ->
        (raw_text, latency_ms)`` (see probe.providers
        .OpenAICompatibleProvider). Required when mock=False.
        Suites containing a ``tool_calling`` category additionally
        require ``complete_ex(model, system, user, tools=...,
        max_tokens=...) -> CompletionResult``.  When ``complete_ex``
        is available it is also used for text canaries so token
        usage (Feature B) is captured; otherwise usage stays None.
    suite_version:
        Version string stamped on every result.  Defaults to
        SUITE_VERSION ("v1.0.0") for the default suite; pass
        SUITE_VERSION_V1_1 when running CANARY_SUITE_V1_1.

    Returns
    -------
    list[CanaryResult]
        One result per prompt, in suite order.
        Raw output is consumed and discarded; only derived features
        are returned.

    #SG-TRACE: REQ-CANARY-017
    #   | assumption: live calls require an explicit provider and a
    #     completed provider ToS review (see docs/PROVIDER_TOS_CHECKS.md)
    #   | test: test_execute_canary_live_requires_provider
    """
    if suite is None:
        suite = CANARY_SUITE_V1
    if suite_version is None:
        suite_version = SUITE_VERSION

    if not mock and provider is None:
        raise ValueError(
            "Live execution requires a provider. Pass "
            "provider=OpenAICompatibleProvider(...) or set mock=True."
        )

    # complete_ex is the richer entry point (tools + usage capture);
    # legacy duck-typed providers exposing only complete() still work
    # for text canaries (tokens stay None).
    complete_ex = getattr(provider, "complete_ex", None)

    results: list[CanaryResult] = []
    ts = datetime.now(tz=timezone.utc).isoformat()
    model_name = model_name_from_tuple(model_tuple)

    for prompt in suite:
        pid = prompt["prompt_id"]
        is_tool = prompt.get("category") == "tool_calling"
        tool_call_valid: bool | None = None
        output_tokens: int | None = None
        reasoning_tokens: int | None = None

        if mock:
            # SG-TRACE: REQ-TOOLCAN-005
            #   | assumption: mock path is offline-only; tool canaries
            #     score against the frozen mock tool_calls JSON
            #   | test: test_execute_canary_mock_tool_suite
            if is_tool:
                raw_output: str = _mock_tool_calls_for(pid)
                tool_call_valid = _is_tool_call_valid(raw_output or None)
            else:
                raw_output = _mock_text_for(pid)
            latency_ms = -1
        elif is_tool:
            # SG-TRACE: REQ-TOOLCAN-006
            #   | assumption: tool canaries require complete_ex; a
            #     provider without tools support fails loudly rather
            #     than silently emitting tool_call_valid=False
            #   | test: test_execute_canary_tool_requires_complete_ex
            if complete_ex is None:
                raise ValueError(
                    "Suite contains a tool_calling canary but the "
                    "provider does not expose complete_ex(...); use "
                    "probe.providers.OpenAICompatibleProvider."
                )
            res = complete_ex(
                model_name,
                prompt["system"],
                prompt["user"],
                tools=[FROZEN_TOOL_SCHEMA_V1],
                max_tokens=TOOL_CANARY_MAX_TOKENS,
            )
            # Fingerprint the tool_calls JSON when present, else the
            # (unexpected) prose answer -- either way only hash/length
            # survive.
            raw_output = res.tool_calls_json or res.text
            tool_call_valid = _is_tool_call_valid(res.tool_calls_json)
            output_tokens = res.output_tokens
            reasoning_tokens = res.reasoning_tokens
            latency_ms = res.latency_ms
        elif complete_ex is not None:
            # SG-TRACE: REQ-TOKMET-002
            #   | assumption: usage capture for text canaries is free
            #     when the provider supports complete_ex; behavior is
            #     otherwise identical to the legacy complete() path
            #   | test: test_execute_canary_captures_usage_tokens
            res = complete_ex(model_name, prompt["system"], prompt["user"])
            raw_output = res.text
            output_tokens = res.output_tokens
            reasoning_tokens = res.reasoning_tokens
            latency_ms = res.latency_ms
        else:
            raw_output, latency_ms = provider.complete(  # type: ignore
                model_name, prompt["system"], prompt["user"]
            )

        result = CanaryResult(
            timestamp=ts,
            model_tuple=model_tuple,
            suite_version=suite_version,
            prompt_id=pid,
            response_hash=_hash_output(raw_output),
            output_length=len(raw_output),
            json_valid=(
                _is_json_valid(raw_output)
                if prompt.get("category") == "structured_output"
                else False
            ),
            latency_ms=latency_ms,
            tool_call_valid=tool_call_valid,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
        )
        # raw_output is explicitly NOT stored; discard here
        del raw_output
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Discard-on-partial runner (contract CAN-2 s7 R1)
# ---------------------------------------------------------------------------


class PartialSuiteError(RuntimeError):
    """Raised when a suite run produced fewer results than prompts.

    Every flush metric is a mean over n=result_count records and the
    substitution-DP sensitivity is MAX/n.  A partial run therefore
    changes BOTH the metric and the noise scale of the stream it feeds:
    a leg that answered 38 of 50 prompts emits a mean over a different,
    provider-selected subset of the corpus at a 1.3x wider noise scale,
    and the CUSUM baseline cannot tell that apart from real drift.
    The decision (contract R1) is discard-on-partial: the caller gets
    this exception and NOTHING is staged for aggregation.

    Attributes:
        completed: Number of prompts that produced a result.
        expected: Number of prompts in the suite.
        failed_prompt_ids: Ids that did not produce a result, in suite
            order.  Ids only -- no provider error text, which could
            carry prompt or output fragments across the privacy
            perimeter.

    #SG-TRACE: REQ-CAN2-013
    #   | assumption: a partial suite must never be flushed at reduced
    #     n; the caller either retries the whole suite or skips the
    #     window entirely
    #   | test: test_partial_suite_run_is_discarded_not_flushed
    """

    def __init__(
        self,
        completed: int,
        expected: int,
        failed_prompt_ids: list[str],
    ) -> None:
        self.completed = completed
        self.expected = expected
        self.failed_prompt_ids = list(failed_prompt_ids)
        super().__init__(
            f"Partial canary suite discarded: {completed}/{expected} "
            f"prompts completed; failed ids={self.failed_prompt_ids}. "
            "Flushing at reduced n would change the DP sensitivity "
            "(MAX/n) of the stream."
        )


# ---------------------------------------------------------------------------
# Pacing + transient-failure backoff (contract CAN-2a s3-s5)
# ---------------------------------------------------------------------------

# Only these two HTTP statuses mean "the same request may succeed if you
# ask again later".  429 is a rate limit, 503 is a temporarily
# unavailable upstream.  Everything else -- 400 bad request, 401/403 bad
# key, 404 wrong model, 500 -- is a fault that a retry cannot fix and
# that must fail the prompt immediately, exactly as before CAN-2a.
# SG-TRACE: REQ-CAN2A-003
#   | assumption: 429/503 are the only statuses worth re-issuing a
#     temperature-0 canary for; retrying a 4xx that is not 429 would
#     spend quota to obtain the identical failure
#   | test: test_p5_non_transient_status_is_not_retried
TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({429, 503})

# Extra attempts per prompt on top of the first one (contract C4).
DEFAULT_MAX_RETRIES: int = 2

# First backoff wait; each further wait doubles it (5s, 10s, 20s...).
# A 429 from a per-minute quota is only cleared by the quota window
# rolling, so sub-second waits are pointless; 5s is the smallest wait
# that plausibly clears a 15 req/min bucket without the leg stalling.
RETRY_BACKOFF_BASE_MS: int = 5_000

# Hard ceiling on the TOTAL backoff a single run may spend (contract
# C4).  Without it, a 50-prompt suite against a provider that 429s
# every call would spend 50 * (5s + 10s) = 12.5 minutes of pure
# sleeping and blow the 15-minute GitHub Actions job timeout.  Once the
# budget is exhausted the remaining prompts fail without retrying and
# the run is discarded as usual -- fast failure, not a slow one.
# SG-TRACE: REQ-CAN2A-004
#   | assumption: a run-scoped budget bounds added wall-clock
#     independently of suite size, delay, and max_retries, so no
#     configuration can make a leg run forever
#   | test: test_p4_transient_forever_is_bounded_by_total_budget
DEFAULT_MAX_TOTAL_BACKOFF_MS: int = 60_000


def _is_transient(exc: BaseException) -> bool:
    """True iff *exc* is a ProviderError with a transient HTTP status.

    Classification is STRUCTURAL: it reads ``ProviderError.status_code``
    (REQ-CAN2A-001) and never inspects the message text.  An error with
    ``status_code is None`` -- a transport failure, a non-JSON body, a
    schema error, or a ProviderError raised by test code without the
    keyword -- is therefore not transient and is not retried.

    #SG-TRACE: REQ-CAN2A-003
    #   | assumption: only the transport's HTTPError branch knows a real
    #     status; anything else genuinely has none, and guessing one by
    #     parsing the message would resurrect the string contract C3
    #     forbids
    #   | test: test_p7_transport_failure_has_no_status_and_is_not_retried
    """
    if not isinstance(exc, ProviderError):
        return False
    return exc.status_code in TRANSIENT_STATUS_CODES


def _backoff_ms(attempt: int, backoff_base_ms: int) -> int:
    """Wait before retry number *attempt* (1-based), exponential.

    attempt 1 -> base, attempt 2 -> 2*base, attempt 3 -> 4*base ...
    Strictly increasing for any positive base, which is what stops a
    retry storm from deepening the rate limit it is reacting to (R2).

    #SG-TRACE: REQ-CAN2A-005
    #   | assumption: a fixed base doubled per attempt is enough backoff
    #     structure for a bounded 2-retry budget; jitter is deliberately
    #     absent so the wait sequence stays deterministic and testable
    #   | test: test_p3_transient_then_success_waits_strictly_increase
    """
    return backoff_base_ms * (2 ** (attempt - 1))


def pacing_budget_ms(
    prompt_count: int,
    delay_ms: int,
    max_total_backoff_ms: int = DEFAULT_MAX_TOTAL_BACKOFF_MS,
) -> int:
    """Upper bound on wall-clock a paced run can ADD, in milliseconds.

    ``(prompt_count - 1) * delay_ms`` is the pacing component (there is
    no sleep before the first prompt or after the last), and
    ``max_total_backoff_ms`` is the run-scoped retry ceiling.  Provider
    latency is not counted: this is the added time only.

    Operators size a leg with this function rather than with arithmetic
    in a comment, and A8 asserts the google setting against it.

    #SG-TRACE: REQ-CAN2A-006
    #   | assumption: the two components are additive and independent;
    #     retry waits never replace pacing waits, they are spent on top
    #   | test: test_p8_google_leg_pacing_budget_fits_actions_timeout
    """
    if prompt_count <= 1:
        paced = 0
    else:
        paced = (prompt_count - 1) * max(0, delay_ms)
    return paced + max(0, max_total_backoff_ms)


def execute_canary_strict(
    model_tuple: str,
    suite: list[dict[str, str]] | None = None,
    mock: bool = True,
    provider: object | None = None,
    suite_version: str | None = None,
    delay_ms: int = 0,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_ms: int = RETRY_BACKOFF_BASE_MS,
    max_total_backoff_ms: int = DEFAULT_MAX_TOTAL_BACKOFF_MS,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[CanaryResult]:
    """Run a suite all-or-nothing: complete, or raise and discard.

    ``execute_canary`` aborts on the first provider failure, which
    loses the results already gathered and tells the caller nothing
    about how much of the corpus is reachable.  This wrapper instead
    tolerates a per-prompt failure (contract R1: one 503 from a free
    tier must not fail the whole leg), keeps going to the end of the
    suite, and then refuses to return anything at all unless every
    prompt produced a result.

    Configuration errors (no provider in live mode, a tool canary
    against a provider without ``complete_ex``) are checked up front
    and still fail loudly as ValueError -- they are not per-prompt
    failures and must not be masked as a partial run.

    Pacing (CAN-2a).  ``delay_ms`` sleeps BETWEEN prompt attempts --
    never before the first and never after the last, so a suite of n
    prompts sleeps exactly n-1 times.  A rate-limited free tier
    (google/gemini-3.5-flash-lite served 18 of 50 sequential calls on
    2026-07-31) can then complete the corpus, while a leg that does not
    need pacing keeps ``delay_ms=0`` and is bit-for-bit unchanged: at 0
    the sleeper is not called at all.

    Backoff (CAN-2a).  A prompt whose ProviderError carries a transient
    status (429, 503) is re-attempted up to ``max_retries`` times with
    exponentially increasing waits, bounded run-wide by
    ``max_total_backoff_ms``.  Retries happen strictly WITHIN one
    prompt attempt: they make a complete run more likely, they do not
    weaken discard-on-partial.  A prompt that still fails after its
    retries fails, and the whole run is still discarded (contract C5).

    Parameters
    ----------
    model_tuple, suite, mock, provider, suite_version:
        As ``execute_canary``.
    delay_ms:
        Inter-prompt pacing in milliseconds.  Default 0 = no pacing.
    max_retries:
        Extra attempts per prompt for transient failures.  Default 2.
        0 disables retrying entirely (pre-CAN-2a behaviour).
    backoff_base_ms:
        First retry wait; doubled per further attempt.
    max_total_backoff_ms:
        Hard ceiling on the total backoff one run may spend.  When it
        is exhausted the remaining prompts fail without retrying.
    sleeper:
        Injected sleep function taking SECONDS, defaulting to
        ``time.sleep``.  Tests pass a recorder so the suite never
        really sleeps (contract C7).

    Returns
    -------
    list[CanaryResult]
        Exactly ``len(suite)`` results, in suite order.

    Raises
    ------
    PartialSuiteError
        If any prompt failed.  No results are returned; the caller
        must not stage anything for this window.
    ValueError
        On a configuration error (see above).

    #SG-TRACE: REQ-CAN2-013
    #   | assumption: per-prompt isolation is achieved by running each
    #     prompt as a one-prompt suite, so this wrapper cannot drift
    #     from execute_canary's per-prompt semantics
    #   | test: test_partial_suite_run_is_discarded_not_flushed
    #   | test: test_strict_runner_returns_full_suite_when_complete
    #SG-TRACE: REQ-CAN2A-007
    #   | assumption: pacing and retrying change only WHEN calls are
    #     made, never which features are derived from them, so the
    #     emitted metrics of a paced run equal those of an unpaced run
    #     over the same provider responses
    #   | test: test_adv2_paced_and_unpaced_metrics_are_identical
    #SG-TRACE: REQ-CAN2A-008
    #   | assumption: every keyword added by CAN-2a has a default that
    #     reproduces the pre-CAN-2a code path, so all existing call
    #     sites and tests stay valid without edits
    #   | test: test_p1_delay_zero_is_bit_for_bit_current_behaviour
    """
    if suite is None:
        suite = CANARY_SUITE_V1
    if not mock and provider is None:
        raise ValueError(
            "Live execution requires a provider. Pass "
            "provider=OpenAICompatibleProvider(...) or set mock=True."
        )
    has_tool = any(p.get("category") == "tool_calling" for p in suite)
    no_tool_support = getattr(provider, "complete_ex", None) is None
    if not mock and has_tool and no_tool_support:
        raise ValueError(
            "Suite contains a tool_calling canary but the provider "
            "does not expose complete_ex(...); use "
            "probe.providers.OpenAICompatibleProvider."
        )

    results: list[CanaryResult] = []
    failed: list[str] = []
    backoff_spent_ms = 0
    for index, prompt in enumerate(suite):
        # SG-TRACE: REQ-CAN2A-009
        #   | assumption: pacing belongs BETWEEN prompts, so a suite of
        #     n prompts sleeps n-1 times; sleeping before the first
        #     prompt would add latency that buys nothing and sleeping
        #     after the last would delay the flush for no reason
        #   | test: test_p2_fifty_prompts_sleep_exactly_forty_nine_times
        if index and delay_ms > 0:
            sleeper(delay_ms / 1000.0)

        attempt = 0
        while True:
            try:
                results.extend(
                    execute_canary(
                        model_tuple,
                        suite=[prompt],
                        mock=mock,
                        provider=provider,
                        suite_version=suite_version,
                    )
                )
                break
            except Exception as exc:
                # Error text is deliberately not retained: provider
                # exceptions may quote request or response fragments.
                # Only the STRUCTURED status is consulted.
                attempt += 1
                remaining_ms = max_total_backoff_ms - backoff_spent_ms
                wait_ms = min(
                    _backoff_ms(attempt, backoff_base_ms), remaining_ms
                )
                # SG-TRACE: REQ-CAN2A-010
                #   | assumption: a retry is worth attempting only when
                #     the failure is transient, the per-prompt budget is
                #     not spent, and the run-wide backoff ceiling still
                #     has room; otherwise the prompt fails now and the
                #     run is discarded exactly as before CAN-2a
                #   | test: test_p6_one_transient_prompt_still_yields_50
                if (
                    attempt > max_retries
                    or wait_ms <= 0
                    or not _is_transient(exc)
                ):
                    failed.append(prompt["prompt_id"])
                    break
                backoff_spent_ms += wait_ms
                sleeper(wait_ms / 1000.0)

    if failed or len(results) != len(suite):
        raise PartialSuiteError(len(results), len(suite), failed)
    return results
