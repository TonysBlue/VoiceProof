from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

from .text import extract_numbers, tokens


def inspect(script: str, transcript: str, terms: Iterable[str] = ()) -> dict:
    expected, observed = tokens(script), tokens(transcript)
    issues: list[dict] = []
    matcher = SequenceMatcher(a=expected, b=observed, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"delete": "omission", "insert": "repetition", "replace": "substitution"}[tag]
        issues.append({
            "type": kind,
            "script_tokens": expected[i1:i2],
            "transcript_tokens": observed[j1:j2],
            "script_range": [i1, i2],
            "transcript_range": [j1, j2],
            "review_required": True,
        })
    if extract_numbers(script) != extract_numbers(transcript):
        issues.append({"type": "number_mismatch", "expected": extract_numbers(script), "observed": extract_numbers(transcript), "review_required": True})
    for term in terms:
        term_tokens = tokens(term)
        def contains(sequence):
            return any(sequence[i:i + len(term_tokens)] == term_tokens for i in range(len(sequence) - len(term_tokens) + 1))
        if term_tokens and contains(expected) and not contains(observed):
            issues.append({"type": "term_mismatch", "term": term, "review_required": True})
    return {
        "schema_version": "voiceproof-report/v1",
        "check": "text_alignment",
        "script_token_count": len(expected),
        "transcript_token_count": len(observed),
        "similarity": round(matcher.ratio(), 4),
        "issues": issues,
        "disclaimer": "疑似问题需由用户结合原音复核。",
    }

