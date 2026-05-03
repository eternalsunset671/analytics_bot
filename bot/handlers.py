"""Telegram-хендлеры команд и документов."""

from __future__ import annotations

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import ContextTypes

from agent import MAX_INSTRUCTION_LEN, run_agent, sanitize_instruction
from bot.replies import safe_reply, send_charts
from bot.state import forget_user_file, get_df, remember_user_file
from data.loader import load_file

logger = logging.getLogger(__name__)


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
    forget_user_file(update.effective_chat.id)
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
    remember_user_file(chat_id, tmp.name)

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
            "Добавьте подпись к файлу с инструкцией — либо вызовите команду:\n"
            "\n"
            "/summary — общий разведочный анализ\n"
            "/anomalies — фокус на выбросах и аномалиях\n"
            "/correlations — фокус на корреляциях\n"
            "/trends — фокус на временных трендах\n"
            "/analyze <инструкция> — анализ по вашей инструкции"
        )


def _parse_args(context: ContextTypes.DEFAULT_TYPE) -> str:
    return " ".join(context.args or []).strip()


async def _run_and_send(update: Update, df, instruction: str, focus_hint: str | None = None):
    await update.message.reply_text("🤖 Агент запускается и пишет код для анализа…")
    kwargs: dict = {
        "user_instruction": instruction,
        "trace_label": update.effective_chat.id,
    }
    if focus_hint:
        kwargs["focus_hint"] = focus_hint
    elif instruction:
        # Свободная инструкция от пользователя — она и есть фокус.
        kwargs["focus_hint"] = (
            "Выполни задачу, описанную в <user_instruction>, как основной фокус анализа. "
            "Не растекайся в общий разведочный обзор, если это явно не запрошено."
        )

    try:
        report, charts, trace_path = run_agent(df, **kwargs)
    except Exception as e:
        logger.exception("agent failed")
        await update.message.reply_text(f"Ошибка агента: {e}")
        return

    await safe_reply(update, f"🧠 *Отчёт агента*\n\n{report}")
    await send_charts(update, charts)

    if trace_path and os.path.exists(trace_path):
        try:
            with open(trace_path, "rb") as fh:
                await update.message.reply_document(
                    document=fh,
                    filename=os.path.basename(trace_path),
                    caption="📝 Трейс агента: рассуждения LLM и сгенерированный код по шагам.",
                )
        except Exception as e:
            logger.warning("Не удалось отправить трейс: %s", e)


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
