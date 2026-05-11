from __future__ import annotations

import re


NUMBER_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


def extract_numbers(text: str) -> list[float]:
    return [float(match.group()) for match in NUMBER_PATTERN.finditer(text)]


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def extract_key_sentences(text: str, keywords: list[str], limit: int = 5) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", normalize_whitespace(text))
    lowered_keywords = [keyword.lower() for keyword in keywords]
    matches = [
        sentence
        for sentence in sentences
        if any(keyword in sentence.lower() for keyword in lowered_keywords)
    ]
    return matches[:limit]
