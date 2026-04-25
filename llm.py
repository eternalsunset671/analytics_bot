import requests

from settings import settings

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2000,
    temperature: float = 0.2,
    timeout: int = 120,
) -> dict:
    """Низкоуровневый вызов Groq Chat Completions. Возвращает сообщение ассистента (dict)."""
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

    response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]


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
