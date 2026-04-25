import logging
import time

import requests

from settings import settings

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_RETRIES = 3
MAX_BACKOFF_SEC = 30


class LLMRateLimitError(Exception):
    """Groq вернул 429 даже после ретраев."""


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
    timeout: int = 120,
) -> dict:
    """Низкоуровневый вызов Groq Chat Completions.

    На 429 (rate limit) уважает заголовок Retry-After и делает до MAX_RETRIES попыток
    с экспоненциальной задержкой. На исчерпании — поднимает LLMRateLimitError
    с понятным сообщением.
    """
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": settings.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_429: requests.Response | None = None
    for attempt in range(MAX_RETRIES):
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)

        if response.status_code == 429:
            last_429 = response
            wait = _parse_retry_after(response.headers.get("retry-after"))
            if wait <= 0:
                wait = min(2 ** attempt, MAX_BACKOFF_SEC)
            wait = min(wait, MAX_BACKOFF_SEC)
            logger.warning(
                "Groq 429 rate limit, попытка %d/%d, жду %.1f c",
                attempt + 1, MAX_RETRIES, wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            break

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]

    detail = ""
    if last_429 is not None:
        try:
            detail = last_429.json().get("error", {}).get("message", "") or last_429.text[:300]
        except Exception:
            detail = last_429.text[:300]
    raise LLMRateLimitError(
        "Groq API: исчерпан лимит запросов или токенов. "
        "Подождите минуту и попробуйте снова. " + (f"Детали: {detail}" if detail else "")
    )


def ask_llm(system_prompt: str, user_message: str, max_tokens: int = 1500) -> str:
    """Совместимый интерфейс для простых текстовых запросов без tool-use."""
    msg = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
    )
    return msg.get("content") or ""
