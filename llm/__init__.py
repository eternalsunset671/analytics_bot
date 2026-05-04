"""Тонкая обёртка над Groq Chat Completions с поддержкой tool-calling."""

from llm.client import ask_llm, chat_completion
from llm.errors import LLMRateLimitError

__all__ = ["LLMRateLimitError", "ask_llm", "chat_completion"]
