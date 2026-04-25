"""Точка входа: настройка логирования, проверка .env, регистрация хендлеров, polling."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import (
    analyze_cmd,
    anomalies_cmd,
    correlations_cmd,
    demo_cmd,
    handle_document,
    help_cmd,
    start,
    summary_cmd,
    trends_cmd,
)
from settings import settings


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )


def _check_env() -> bool:
    if not settings.telegram_bot_token or settings.telegram_bot_token == "your_token_here":
        print("Ошибка: укажите TELEGRAM_BOT_TOKEN в .env")
        return False
    if not settings.groq_api_key or settings.groq_api_key == "your_api_key_here":
        print("Ошибка: укажите GROQ_API_KEY в .env")
        return False
    return True


def main() -> None:
    _setup_logging()
    if not _check_env():
        return

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("demo", demo_cmd))
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("anomalies", anomalies_cmd))
    app.add_handler(CommandHandler("correlations", correlations_cmd))
    app.add_handler(CommandHandler("trends", trends_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
