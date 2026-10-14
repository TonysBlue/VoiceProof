from __future__ import annotations

import re


def tokens(value: str) -> list[str]:
    """Tokenize Chinese characters, numbers and Latin words deterministically."""
    return re.findall(r"[\u4e00-\u9fff]|\d+(?:\.\d+)?|[A-Za-z]+", value.lower())


def extract_numbers(value: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", value)

