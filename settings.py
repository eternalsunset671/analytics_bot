from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = "your_token_here"
    groq_api_key: str = "your_api_key_here"
    model: str = "llama-3.3-70b-versatile"
    debug_traces: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
