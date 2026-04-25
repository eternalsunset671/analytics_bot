"""Изолированное выполнение Python-кода, сгенерированного LLM."""

from __future__ import annotations

import io
import re
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

EXEC_TIMEOUT_SEC = 25
MAX_TOOL_OUTPUT_CHARS = 4000
MAX_CHARTS = 8

# Паттерны, которые никогда не должны появляться в коде, сгенерированном LLM.
# Цель — не допустить побочных эффектов вне анализа данных.
DANGEROUS_PATTERNS: list[str] = [
    r"\bimport\s+os\b",
    r"\bimport\s+subprocess\b",
    r"\bimport\s+sys\b",
    r"\bimport\s+socket\b",
    r"\bimport\s+shutil\b",
    r"\bimport\s+pathlib\b",
    r"\bimport\s+requests\b",
    r"\bimport\s+urllib\b",
    r"\bimport\s+httpx\b",
    r"\bfrom\s+os\b",
    r"\bfrom\s+subprocess\b",
    r"\bfrom\s+sys\b",
    r"\bfrom\s+pathlib\b",
    r"\b__import__\s*\(",
    r"\bopen\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bos\.",
    r"\bsubprocess\.",
    r"\bsys\.",
    r"\bsocket\.",
    r"\.read_csv\s*\(",
    r"\.read_excel\s*\(",
    r"\.read_parquet\s*\(",
    r"\.to_csv\s*\(",
    r"\.to_excel\s*\(",
    r"\.to_parquet\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"__class__",
    r"__bases__",
    r"__subclasses__",
]


def is_code_safe(code: str) -> tuple[bool, str]:
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, code, flags=re.IGNORECASE):
            return False, f"код отклонён: запрещённый паттерн `{pat}`"
    return True, ""


def run_code(code: str, df: pd.DataFrame, charts: list[io.BytesIO]) -> str:
    """Выполняет python-код LLM в ограниченном окружении, возвращает текст результата."""
    ok, reason = is_code_safe(code)
    if not ok:
        return f"ERROR: {reason}"

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    existing_figs = set(plt.get_fignums())

    globals_dict: dict = {
        "__builtins__": __builtins__,
        "df": df.copy(),
        "pd": pd,
        "np": np,
        "plt": plt,
    }

    error_holder: dict = {"traceback": None}

    def target() -> None:
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(code, globals_dict)  # noqa: S102 — преднамеренно, под контролем
        except Exception:
            error_holder["traceback"] = traceback.format_exc(limit=5)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(EXEC_TIMEOUT_SEC)

    if thread.is_alive():
        return f"ERROR: превышен таймаут выполнения ({EXEC_TIMEOUT_SEC} c)."

    new_figs = sorted(set(plt.get_fignums()) - existing_figs)
    saved = 0
    for fig_num in new_figs:
        if len(charts) >= MAX_CHARTS:
            plt.close(fig_num)
            continue
        fig = plt.figure(fig_num)
        try:
            fig.tight_layout()
        except Exception:
            pass
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
            buf.seek(0)
            charts.append(buf)
            saved += 1
        finally:
            plt.close(fig)

    parts: list[str] = []
    out = stdout_buf.getvalue()
    err = stderr_buf.getvalue()
    if out:
        parts.append(f"STDOUT:\n{out}")
    if err:
        parts.append(f"STDERR:\n{err}")
    if error_holder["traceback"]:
        parts.append(f"EXCEPTION:\n{error_holder['traceback']}")
    if saved:
        parts.append(f"[Сохранено графиков: {saved}]")
    if not parts:
        parts.append("[код выполнен успешно, нет текстового вывода]")

    response = "\n\n".join(parts)
    if len(response) > MAX_TOOL_OUTPUT_CHARS:
        response = response[:MAX_TOOL_OUTPUT_CHARS] + "\n…(вывод обрезан)"
    return response
