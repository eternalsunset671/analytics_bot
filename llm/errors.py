class LLMRateLimitError(Exception):
    """Groq вернул 429 даже после ретраев."""
