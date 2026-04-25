"""Защита от prompt-injection в пользовательской инструкции."""

from __future__ import annotations

import re

MAX_INSTRUCTION_LEN = 1000

INJECTION_PATTERNS: list[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(the\s+)?(previous|system)\s+(instructions|prompt)",
    r"забудь\s+(все\s+)?(предыдущие|системные|прошлые)?\s*инструкци",
    r"игнорируй\s+(все\s+)?(предыдущие|системные)?\s*инструкци",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"(show|print|output)\s+(me\s+)?(your\s+)?system\s+prompt",
    r"раскрой\s+(свой\s+)?(системный\s+)?промпт",
    r"выведи\s+(свой\s+)?(системный\s+)?промпт",
    r"\bjailbreak\b",
    r"\bDAN\s+mode\b",
    r"ты\s+теперь\s+",
    r"you\s+are\s+now\s+",
    r"act\s+as\s+(a|an)\s+",
    r"pretend\s+to\s+be\s+",
    r"override\s+(the\s+)?(system|safety)",
]


def sanitize_instruction(text: str | None) -> tuple[str, bool]:
    """Обрезает инструкцию и сигнализирует о признаках prompt-injection."""
    if not text:
        return "", False
    cleaned = text.strip()[:MAX_INSTRUCTION_LEN]
    suspicious = any(re.search(p, cleaned, flags=re.IGNORECASE) for p in INJECTION_PATTERNS)
    return cleaned, suspicious
