"""
tests.test_suite_corpus_pinned
==============================
Golden-hash gate for the content-addressed canary corpora.

Why this file exists
--------------------
``test_canary_suite_v2.py`` asserts that the suite hash is *stable*
(the same value twice, and the same value in a second interpreter) and
that it *differs* between v1.1.0 and v2.0.0.  Both sides of every one
of those assertions are recomputed from the corpus that is in
``probe/canary.py`` at the moment the test runs, so an edit to a prompt
text moves both sides together and the suite still passes.  Prompt ids,
category counts, entry key shape and prefix identity are pinned; the
prompt TEXT is not.

The architectural invariant is "never mutate a historical baseline".
Until this file existed nothing in the gate enforced it.  A silent
corpus edit would not fail a test -- it would quietly make every
historical time-series incomparable, which is precisely the failure the
content-addressing scheme exists to prevent.

A literal digest checked into the repository is the only representation
of a corpus that an edit to that corpus cannot move.

#SG-TRACE: REQ-BENCH1-001
#   | assumption: SHA-256 over canonical JSON is reproducible on every
#     supported interpreter, so a literal digest is a valid gate
#   | test: test_v2_corpus_hash_is_pinned
"""

from __future__ import annotations

import copy

from probe.canary import (
    CANARY_SUITE_V1_1,
    CANARY_SUITE_V2,
    FROZEN_TOOL_SCHEMA_V1,
    suite_content_hash,
)

# Measured on 2026-09-19 from main @45d7846, the corpus that every
# published SEISMOGRAPH measurement to date was collected against.
# Changing a value here is never a fix: it is a new suite version.
PINNED_V2_WITH_TOOLS = (
    "d4fbb0a0ee7f704accc2b91c2832a4905cdf7b5cb175785490eabe878b9aba14"
)
PINNED_V2_NO_TOOLS = (
    "2fa1bb7bc9c2b43636fcf80eb5b76b20ce861c24a729bac07badf4953b37422b"
)
PINNED_V1_1_WITH_TOOLS = (
    "62422b5875d6ec785829d715f7155305cb322bb0a85c5525ab73f20bf86808c8"
)

_TOOLS = [FROZEN_TOOL_SCHEMA_V1]


def test_v2_corpus_hash_is_pinned() -> None:
    """The v2.0.0 corpus still hashes to its historical digest.

    #SG-TRACE: REQ-BENCH1-001 | test: (this)
    """
    assert suite_content_hash(CANARY_SUITE_V2, _TOOLS) == (
        PINNED_V2_WITH_TOOLS
    )
    assert suite_content_hash(CANARY_SUITE_V2) == PINNED_V2_NO_TOOLS


def test_v1_1_corpus_hash_is_pinned() -> None:
    """The frozen v1.1.0 prefix still hashes to its historical digest.

    #SG-TRACE: REQ-BENCH1-001 | test: (this)
    """
    assert suite_content_hash(CANARY_SUITE_V1_1, _TOOLS) == (
        PINNED_V1_1_WITH_TOOLS
    )


def test_single_character_edit_moves_the_hash() -> None:
    """ADVERSARIAL: a forged corpus claiming to be v2.0.0.

    One character changed in one prompt of fifty.  This is the Sybil
    case at corpus level: an observer that reports suite_version
    "v2.0.0" while running something else.  The digest must separate
    them.

    #SG-TRACE: REQ-BENCH1-002
    #   | assumption: SHA-256 avalanche makes any edit detectable
    #   | test: (this)
    """
    forged = copy.deepcopy(CANARY_SUITE_V2)
    forged[7]["user"] = forged[7]["user"] + "."
    assert suite_content_hash(forged, _TOOLS) != PINNED_V2_WITH_TOOLS


def test_reordering_moves_the_hash() -> None:
    """ADVERSARIAL: same fifty prompts, different order.

    Prompt order is part of the corpus identity because results are
    returned in suite order and prompt_id alone does not fix position.

    #SG-TRACE: REQ-BENCH1-002 | test: (this)
    """
    reordered = copy.deepcopy(CANARY_SUITE_V2)
    reordered[10], reordered[11] = reordered[11], reordered[10]
    assert suite_content_hash(reordered, _TOOLS) != PINNED_V2_WITH_TOOLS


def test_tool_schema_edit_moves_the_hash() -> None:
    """ADVERSARIAL: provider-visible change with no prompt change.

    A tool schema edit alters what the model is asked to emit while
    every prompt text stays byte-identical.  Without folding the
    schemas into the digest this is invisible; with them it is a new
    corpus.

    #SG-TRACE: REQ-BENCH1-003
    #   | assumption: schema identity is part of corpus identity
    #   | test: (this)
    """
    tampered = copy.deepcopy(FROZEN_TOOL_SCHEMA_V1)
    tampered["function"]["name"] = tampered["function"]["name"] + "_v2"
    assert suite_content_hash(CANARY_SUITE_V2, [tampered]) != (
        PINNED_V2_WITH_TOOLS
    )
    # ...and the prompts really were untouched.
    assert suite_content_hash(CANARY_SUITE_V2) == PINNED_V2_NO_TOOLS


def test_non_ascii_corpus_hashes_deterministically() -> None:
    """A future non-ASCII corpus must still address deterministically.

    The v2 corpus is ASCII today (test_v2_corpus_is_ascii).  Any
    pluggable or user-supplied suite will not be, and ``ensure_ascii``
    escaping is what keeps the digest independent of locale and file
    encoding.

    #SG-TRACE: REQ-BENCH1-004
    #   | assumption: json.dumps(ensure_ascii=True) is locale-
    #     independent, so the digest is portable across hosts
    #   | test: (this)
    """
    suite = [
        {
            "prompt_id": "unicode-probe",
            "category": "logic",
            "system": "Svar kort.",
            "user": "Hvad er hovedstaden i Danmark? ÆØÅ",
        }
    ]
    first = suite_content_hash(suite)
    assert first == suite_content_hash(copy.deepcopy(suite))
    assert len(first) == 64


def test_pinned_digests_are_wellformed() -> None:
    """Guard the constants themselves against a typo.

    #SG-TRACE: REQ-BENCH1-001 | test: (this)
    """
    for digest in (
        PINNED_V2_WITH_TOOLS,
        PINNED_V2_NO_TOOLS,
        PINNED_V1_1_WITH_TOOLS,
    ):
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
    assert (
        len(
            {
                PINNED_V2_WITH_TOOLS,
                PINNED_V2_NO_TOOLS,
                PINNED_V1_1_WITH_TOOLS,
            }
        )
        == 3
    )
