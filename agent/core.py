"""Агентный цикл: LLM ↔ python_exec до получения финального отчёта."""

from __future__ import annotations

import io
import json
import logging

import pandas as pd

from agent.injection import sanitize_instruction
from agent.prompts import build_system_prompt, build_user_message
from agent.sandbox import run_code
from agent.tools import PYTHON_EXEC_TOOL
from agent.trace import FileTrace, NullTrace, Trace
from llm import LLMRateLimitError, chat_completion
from settings import settings

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8


def _columns_preview(df: pd.DataFrame, limit: int = 40) -> str:
    head = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns[:limit])
    if len(df.columns) > limit:
        head += f", … (+{len(df.columns) - limit})"
    return head


def _make_trace(label: str | int | None) -> Trace:
    return FileTrace(label) if settings.debug_traces else NullTrace()


def run_agent(
    df: pd.DataFrame,
    user_instruction: str = "",
    focus_hint: str = "Проведи всесторонний разведочный анализ датасета.",
    trace_label: str | int | None = None,
) -> tuple[str, list[io.BytesIO], str | None]:
    """Запускает агентный цикл.

    Возвращает (финальный_текст, список_графиков, путь_к_трейсу).
    Путь к трейсу — None, если DEBUG_TRACES=false в .env.
    """
    charts: list[io.BytesIO] = []
    instruction, suspicious = sanitize_instruction(user_instruction)
    columns_preview = _columns_preview(df)

    trace = _make_trace(trace_label)
    system_prompt = build_system_prompt(focus_hint)
    user_content = build_user_message(
        rows=len(df),
        cols=len(df.columns),
        columns_preview=columns_preview,
        instruction=instruction,
        suspicious=suspicious,
    )

    trace.section(
        "DATASET",
        f"{len(df)} rows × {len(df.columns)} cols\nColumns: {columns_preview}",
    )
    trace.section(
        "USER INSTRUCTION",
        (instruction or "(не задано)")
        + ("\n[suspicious=True — детектор prompt-injection]" if suspicious else ""),
    )
    trace.section("FOCUS HINT", focus_hint)
    trace.section("SYSTEM PROMPT", system_prompt)
    trace.section("USER MESSAGE", user_content)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    final_report: str
    try:
        for step in range(MAX_ITERATIONS):
            try:
                msg = chat_completion(messages, tools=[PYTHON_EXEC_TOOL])
            except LLMRateLimitError as e:
                logger.warning("LLM rate-limited at step %d: %s", step, e)
                final_report = (
                    "⏳ Groq API временно ограничивает запросы (rate limit). "
                    "Это часто бывает на бесплатном тарифе при больших датасетах "
                    "или серии запусков подряд. Подождите 30–60 секунд и попробуйте снова."
                )
                trace.section(f"STEP {step + 1} — RATE LIMIT", str(e))
                trace.final(final_report, len(charts))
                return final_report, charts, trace.path
            except Exception as e:
                logger.error("LLM error at step %d: %s", step, e)
                final_report = f"Ошибка LLM: {e}"
                trace.section(f"STEP {step + 1} — LLM ERROR", str(e))
                trace.final(final_report, len(charts))
                return final_report, charts, trace.path

            tool_calls = msg.get("tool_calls") or []
            reasoning = msg.get("content") or ""
            trace.step(step, reasoning, tool_calls)

            assistant_entry: dict = {"role": "assistant", "content": reasoning}
            if tool_calls:
                assistant_entry["tool_calls"] = tool_calls
            messages.append(assistant_entry)

            if not tool_calls:
                final_report = reasoning.strip() or "(LLM вернула пустой ответ.)"
                trace.final(final_report, len(charts))
                return final_report, charts, trace.path

            for i, tc in enumerate(tool_calls, 1):
                name = tc.get("function", {}).get("name")
                args_raw = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                except Exception:
                    args = {}

                if name == "python_exec":
                    code = args.get("code", "") or ""
                    logger.info("agent step %d: python_exec\n%s", step, code[:400])
                    result = run_code(code, df, charts)
                else:
                    result = f"ERROR: неизвестный инструмент '{name}'."

                trace.tool_result(i, result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": name or "python_exec",
                        "content": result,
                    }
                )

        final_report = (
            "Агент достиг лимита итераций, не завершив отчёт. "
            "Попробуйте сформулировать более узкую инструкцию."
        )
        trace.final(final_report, len(charts))
        return final_report, charts, trace.path
    finally:
        trace.close()
