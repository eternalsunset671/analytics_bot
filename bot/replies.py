"""Хелперы для отправки сообщений: безопасный Markdown, отправка графиков."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 3500


def truncate(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(обрезано)"


def escape_md(text: str) -> str:
    """Убираем Markdown-форматирование, чтобы Telegram не сломался на парсинге."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)", "•", text)
    text = text.replace("`", "'")
    return text


async def safe_reply(update: Update, text: str) -> None:
    text = truncate(text)
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest:
        clean = escape_md(text)
        try:
            await update.message.reply_text(clean, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(clean)


async def send_charts(update: Update, charts: list) -> None:
    for buf in charts:
        buf.seek(0)
        try:
            await update.message.reply_photo(photo=buf)
        except Exception as e:
            logger.warning("Не удалось отправить график: %s", e)
