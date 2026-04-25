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

from agent import (
    MAX_INSTRUCTION_LEN,
    run_agent,
    sanitize_instruction,
)
from analytics import load_file
from settings import settings

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

user_files: dict[int, str] = {}

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
        try:
            await update.message.reply_photo(photo=buf)
        except Exception as e:
            logger.warning("Не удалось отправить график: %s", e)


def escape_md(text: str) -> str:
    """Убираем Markdown-форматирование, чтобы Telegram не сломался на парсинге."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)", "•", text)
    text = text.replace("`", "'")
    return text


async def safe_reply(update: Update, text: str):
    text = truncate(text)
    try:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except BadRequest:
        clean = escape_md(text)
        try:
            await update.message.reply_text(clean, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.message.reply_text(clean)


HELP_TEXT = (
    "📊 *AI-аналитик данных*\n\n"
    "Как пользоваться:\n"
    "1) Пришлите CSV или Excel-файл. В подпись к файлу можно добавить "
    "инструкцию — на что обратить внимание (например: «сфокусируйся на аномалиях в выручке»).\n"
    "2) Бот запустит ИИ-агента, который сам напишет и выполнит Python-код "
    "для анализа, построит графики и вернёт отчёт.\n\n"
    "Команды:\n"
    "  /analyze <инструкция> — запустить анализ с вашей инструкцией\n"
    "  /summary — общий разведочный анализ\n"
    "  /anomalies — фокус на выбросах и аномалиях\n"
    "  /correlations — фокус на корреляциях и связях\n"
    "  /trends — фокус на временных трендах и распределениях\n"
    "  /demo — переключиться на демо-датасет (Netflix Titles)\n"
    "  /help — эта справка\n\n"
    f"Длина инструкции — до {MAX_INSTRUCTION_LEN} символов."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def demo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    old = user_files.pop(chat_id, None)
    if old and os.path.exists(old):
        try:
            os.unlink(old)
        except OSError:
            pass
    await update.message.reply_text(
        "Переключено на демо-датасет (Netflix Titles, 8800+ записей).\n"
        "Отправьте /summary, /anomalies, /correlations, /trends "
        "или /analyze <ваша инструкция>."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith((".csv", ".xlsx", ".xls")):
        await update.message.reply_text("Поддерживаются форматы: CSV (.csv), Excel (.xlsx, .xls).")
        return

    await update.message.reply_text("⏳ Загружаю файл…")

    file = await context.bot.get_file(doc.file_id)
    suffix = os.path.splitext(doc.file_name)[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    await file.download_to_drive(tmp.name)
    tmp.close()

    chat_id = update.effective_chat.id
    old = user_files.get(chat_id)
    if old and os.path.exists(old):
        try:
            os.unlink(old)
        except OSError:
            pass
    user_files[chat_id] = tmp.name

    try:
        df = load_file(tmp.name)
    except Exception as e:
        await update.message.reply_text(f"Ошибка чтения файла: {e}")
        return

    caption = (update.message.caption or "").strip()
    instruction, suspicious = sanitize_instruction(caption)

    info_lines = [
        f"✅ Файл загружен: *{doc.file_name}*",
        f"Строк: {len(df)}, Столбцов: {len(df.columns)}",
    ]
    if suspicious:
        info_lines.append(
            "⚠️ В инструкции замечены признаки prompt-injection — агент обработает её "
            "как данные, не как команды."
        )
    await safe_reply(update, "\n".join(info_lines))

    if instruction:
        await _run_and_send(update, df, instruction)
    else:
        await update.message.reply_text(
            "Добавьте подпись к файлу с инструкцией — или вызовите "
            "/summary, /anomalies, /correlations, /trends или /analyze <инструкция>."
        )


def _parse_args(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or []).strip()


async def _run_and_send(update: Update, df, instruction: str, focus_hint: str | None = None):
    await update.message.reply_text("🤖 Агент запускается и пишет код для анализа…")
    kwargs = {"user_instruction": instruction}
    if focus_hint:
        kwargs["focus_hint"] = focus_hint
    try:
        report, charts = run_agent(df, **kwargs)
    except Exception as e:
        logger.exception("agent failed")
        await update.message.reply_text(f"Ошибка агента: {e}")
        return

    await safe_reply(update, f"🧠 *Отчёт агента*\n\n{report}")
    await send_charts(update, charts)


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV/Excel-файл или вызовите /demo.")
        return

    raw = _parse_args(context)
    instruction, suspicious = sanitize_instruction(raw)
    if suspicious:
        await update.message.reply_text(
            "⚠️ В инструкции замечены признаки prompt-injection — агент обработает её "
            "как данные, не как команды."
        )
    if is_demo:
        await update.message.reply_text("ℹ️ Использую демо-датасет.")
    await _run_and_send(update, df, instruction)


async def _shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE, focus_hint: str):
    chat_id = update.effective_chat.id
    df, is_demo = get_df(chat_id)
    if df is None:
        await update.message.reply_text("Сначала отправьте CSV/Excel-файл или вызовите /demo.")
        return
    if is_demo:
        await update.message.reply_text("ℹ️ Использую демо-датасет.")
    extra = _parse_args(context)
    instruction, suspicious = sanitize_instruction(extra)
    if suspicious:
        await update.message.reply_text(
            "⚠️ В инструкции замечены признаки prompt-injection — агент обработает её "
            "как данные, не как команды."
        )
    await _run_and_send(update, df, instruction, focus_hint=focus_hint)


async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _shortcut(
        update,
        context,
        focus_hint=(
            "Сделай общий разведочный анализ: структура датасета, типы, пропуски, "
            "ключевые описательные статистики, 2–4 основных графика распределений."
        ),
    )


async def anomalies_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _shortcut(
        update,
        context,
        focus_hint=(
            "Сфокусируйся на поиске аномалий и выбросов: правило IQR и/или z-score "
            "для числовых столбцов, боксплоты, scatter-графики с подсветкой выбросов. "
            "В отчёте укажи долю выбросов по каждому столбцу и возможные причины."
        ),
    )


async def correlations_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _shortcut(
        update,
        context,
        focus_hint=(
            "Сфокусируйся на корреляциях между числовыми столбцами: посчитай матрицу, "
            "построй heatmap, назови топ-5 сильнейших пар и обсуди возможную "
            "мультиколлинеарность и смысл связей."
        ),
    )


async def trends_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _shortcut(
        update,
        context,
        focus_hint=(
            "Сфокусируйся на временных трендах и распределениях категорий: найди "
            "столбцы с датой/годом, построй динамику, выдели пики и спады; для "
            "категориальных столбцов покажи топ-10."
        ),
    )


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
    app.add_handler(CommandHandler("analyze", analyze_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("anomalies", anomalies_cmd))
    app.add_handler(CommandHandler("correlations", correlations_cmd))
    app.add_handler(CommandHandler("trends", trends_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
