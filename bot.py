import logging
import os
import re
import tempfile

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from analytics import (
    analyze_trends,
    compute_correlations,
    detect_anomalies,
    get_basic_stats,
    load_file,
)
from llm import ask_llm
from settings import settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Хранилище путей к загруженным файлам по chat_id
user_files: dict[int, str] = {}

# Демо-файл (demo.csv в директории проекта)
DEMO_FILE = os.path.join(os.path.dirname(__file__), "demo.csv")


def get_df(chat_id: int):
    path = user_files.get(chat_id)
    if path and os.path.exists(path):
        return load_file(path), False
    if os.path.exists(DEMO_FILE):
        return load_file(DEMO_FILE), True
    return None, False


def truncate(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…(обрезано)"


async def send_charts(update: Update, charts: list):
    for buf in charts:
        buf.seek(0)
        await update.message.reply_photo(photo=buf)


def escape_md(text: str) -> str:
    """Экранирует спецсимволы Markdown v1 в тексте, не трогая уже размеченные блоки."""
    # Убираем markdown-форматирование из LLM-ответа, оставляя чистый текст
    # Заменяем **text** и __text__ на просто text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Экранируем одиночные * и _ чтобы Telegram не пытался их парсить
    text = re.sub(r'(?<!\*)\*(?!\*)', '•', text)
    text = text.replace('`', "'")
    return text


async def safe_reply(update: Update, text: str):
    """Отправляет сообщение, при ошибке Markdown — fallback на plain text."""
    text = truncate(text)
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest:
        # Markdown не валиден — отправляем как plain text
        clean = escape_md(text)
        try:
            await update.message.reply_text(clean, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(clean)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Бот AI-аналитики данных*\n\n"
        "Отправьте CSV-файл, затем используйте команды:\n\n"
        "  /summary — AI-саммари и ключевые метрики\n"
        "  /anomalies — поиск аномалий + графики\n"
        "  /correlations — корреляции + heatmap\n"
        "  /trends — тренды и распределения\n"
        "  /demo — использовать демо-датасет Netflix\n\n"
        "Или просто вызовите команду — бот использует демо-данные.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*Команды:*\n"
        "/summary — AI-саммари данных\n"
        "/anomalies — обнаружение аномалий\n"
        "/correlations — корреляционный анализ\n"
        "/trends — тренды и распределения\n"
        "/demo — переключиться на демо-датасет\n"
        "/start — приветствие",
        parse_mode="Markdown",
    )


async def demo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_files.pop(chat_id, None)
    await update.message.reply_text(
        "Переключено на демо-датасет (Netflix Titles, 8800+ записей).\n"
        "Вызовите /summary, /anomalies, /correlations или /trends."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith((".csv", ".xlsx", ".xls")):
        await update.message.reply_text("Поддерживаются форматы: CSV (.csv), Excel (.xlsx, .xls).")
        return

    await update.message.reply_text("⏳ Загружаю файл...")

    file = await context.bot.get_file(doc.file_id)
    suffix = os.path.splitext(doc.file_name)[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    await file.download_to_drive(tmp.name)
    tmp.close()

    chat_id = update.effective_chat.id
    # Удаляем старый файл
    old = user_files.get(chat_id)
    if old and os.path.exists(old):
        os.unlink(old)

    user_files[chat_id] = tmp.name

    try:
        df = load_file(tmp.name)
        await safe_reply(
            update,
            f"✅ Файл загружен: *{doc.file_name}*\n"
            f"Строк: {len(df)}, Столбцов: {len(df.columns)}\n\n"
            "Теперь вызовите /summary, /anomalies, /correlations или /trends.",
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка чтения файла: {e}")


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV-файл или вызовите /demo.")
        return

    label = " (демо-датасет)" if is_demo else ""
    await update.message.reply_text(f"⏳ Анализирую данные{label}...")

    stats = get_basic_stats(df)
    # Отправляем первые строки данных в LLM
    sample = df.head(5).to_string(max_colwidth=50)

    prompt = (
        "Ты — аналитик данных. Проанализируй статистику датасета и дай краткое "
        "AI-саммари на русском языке. Выдели ключевые метрики, интересные "
        "наблюдения, потенциальные проблемы с качеством данных. "
        "Ответ — 5-10 пунктов, структурированно. "
        "НЕ используй Markdown-форматирование (**, __, ``). Используй обычный текст и символ • для списков."
    )
    user_msg = f"Статистика:\n{stats}\n\nПервые 5 строк:\n{sample}"

    try:
        ai_response = ask_llm(prompt, user_msg)
        text = f"📊 *AI-саммари*{label}\n\n{stats}\n\n🤖 *Интерпретация LLM:*\n{ai_response}"
        await safe_reply(update, text)
    except Exception as e:
        logger.error("LLM error: %s", e)
        text = f"📊 *Статистика*{label}\n\n{stats}\n\n⚠️ LLM недоступен: {e}"
        await safe_reply(update, text)


async def anomalies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV-файл или вызовите /demo.")
        return

    label = " (демо-датасет)" if is_demo else ""
    await update.message.reply_text(f"⏳ Ищу аномалии{label}...")

    report, charts = detect_anomalies(df)

    prompt = (
        "Ты — аналитик данных. Проанализируй найденные аномалии в датасете "
        "и дай интерпретацию на русском языке: что они значат, на что обратить "
        "внимание, какие рекомендации. Ответ — 3-5 пунктов. "
        "НЕ используй Markdown-форматирование (**, __, ``). Используй обычный текст и символ • для списков."
    )
    try:
        ai_response = ask_llm(prompt, f"Результаты поиска аномалий (метод IQR):\n{report}")
        text = f"🔍 *Аномалии*{label}\n\n{report}\n\n🤖 *Интерпретация LLM:*\n{ai_response}"
    except Exception as e:
        logger.error("LLM error: %s", e)
        text = f"🔍 *Аномалии*{label}\n\n{report}\n\n⚠️ LLM недоступен: {e}"

    await safe_reply(update, text)
    await send_charts(update, charts)


async def correlations_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV-файл или вызовите /demo.")
        return

    label = " (демо-датасет)" if is_demo else ""
    await update.message.reply_text(f"⏳ Считаю корреляции{label}...")

    report, charts = compute_correlations(df)

    prompt = (
        "Ты — аналитик данных. Проанализируй корреляции в датасете и дай "
        "интерпретацию на русском: какие связи значимы, что они означают, "
        "есть ли мультиколлинеарность. Ответ — 3-5 пунктов. "
        "НЕ используй Markdown-форматирование (**, __, ``). Используй обычный текст и символ • для списков."
    )
    try:
        ai_response = ask_llm(prompt, f"Корреляционный анализ:\n{report}")
        text = f"📈 *Корреляции*{label}\n\n{report}\n\n🤖 *Интерпретация LLM:*\n{ai_response}"
    except Exception as e:
        logger.error("LLM error: %s", e)
        text = f"📈 *Корреляции*{label}\n\n{report}\n\n⚠️ LLM недоступен: {e}"

    await safe_reply(update, text)
    await send_charts(update, charts)


async def trends_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV-файл или вызовите /demo.")
        return

    label = " (демо-датасет)" if is_demo else ""
    await update.message.reply_text(f"⏳ Анализирую тренды{label}...")

    report, charts = analyze_trends(df)

    prompt = (
        "Ты — аналитик данных. Проанализируй тренды в датасете и дай "
        "интерпретацию на русском: какие тенденции видны, что растёт/падает, "
        "какие категории доминируют. Ответ — 3-5 пунктов. "
        "НЕ используй Markdown-форматирование (**, __, ``). Используй обычный текст и символ • для списков."
    )
    try:
        ai_response = ask_llm(prompt, f"Анализ трендов:\n{report}")
        text = f"📉 *Тренды*{label}\n\n{report}\n\n🤖 *Интерпретация LLM:*\n{ai_response}"
    except Exception as e:
        logger.error("LLM error: %s", e)
        text = f"📉 *Тренды*{label}\n\n{report}\n\n⚠️ LLM недоступен: {e}"

    await safe_reply(update, text)
    await send_charts(update, charts)


def main():
    if not settings.telegram_bot_token or settings.telegram_bot_token == "your_token_here":
        print("Ошибка: укажите TELEGRAM_BOT_TOKEN в .env")
        return
    if not settings.groq_api_key or settings.groq_api_key == "your_api_key_here":
        print("Ошибка: укажите GROQ_API_KEY в .env")
        return

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("demo", demo_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("anomalies", anomalies_cmd))
    app.add_handler(CommandHandler("correlations", correlations_cmd))
    app.add_handler(CommandHandler("trends", trends_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
