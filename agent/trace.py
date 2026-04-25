"""Подробный лог одного запуска агента: системный промпт, инструкция,
рассуждения LLM, сгенерированный код, ответы инструмента, финальный отчёт."""

from __future__ import annotations

import datetime as _dt
import json
import os
import re

TRACES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "traces")


class NullTrace:
    """Заглушка для случая, когда DEBUG_TRACES=false. Все методы — no-op."""

    path: str | None = None

    def section(self, title: str, body: str) -> None:
        return None

    def step(self, step_idx: int, reasoning: str, tool_calls: list[dict]) -> None:
        return None

    def tool_result(self, tool_call_idx: int, result: str) -> None:
        return None

    def final(self, report: str, charts_count: int) -> None:
        return None

    def close(self) -> None:
        return None


class FileTrace:
    """Пишет трейс в отдельный файл traces/trace_<label>_<timestamp>.txt."""

    def __init__(self, label: str | int | None) -> None:
        os.makedirs(TRACES_DIR, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", str(label or "anon"))[:32]
        self.path = os.path.join(TRACES_DIR, f"trace_{safe_label}_{ts}.txt")
        self._fh = open(self.path, "w", encoding="utf-8")
        self._write_header(ts)

    def _write_header(self, ts: str) -> None:
        self._fh.write("=" * 80 + "\n")
        self._fh.write(f"AGENT TRACE — {ts}\n")
        self._fh.write("=" * 80 + "\n\n")

    def section(self, title: str, body: str) -> None:
        self._fh.write(f"\n----- {title} -----\n")
        self._fh.write((body or "").rstrip() + "\n")
        self._fh.flush()

    def step(self, step_idx: int, reasoning: str, tool_calls: list[dict]) -> None:
        self._fh.write(f"\n========== STEP {step_idx + 1} ==========\n")
        if reasoning.strip():
            self._fh.write("LLM reasoning / message:\n")
            self._fh.write(reasoning.rstrip() + "\n")
        else:
            self._fh.write("LLM reasoning / message: (пусто — LLM сразу вызвала инструмент)\n")
        for i, tc in enumerate(tool_calls, 1):
            fn = tc.get("function", {})
            name = fn.get("name", "?")
            raw_args = fn.get("arguments", "")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                args = {"_raw": str(raw_args)}
            code = args.get("code", "") if isinstance(args, dict) else ""
            self._fh.write(f"\n>>> tool_call #{i}: {name}\n")
            if code:
                self._fh.write("--- code ---\n")
                self._fh.write(code.rstrip() + "\n")
                self._fh.write("------------\n")
            else:
                self._fh.write(f"args: {json.dumps(args, ensure_ascii=False)[:1000]}\n")
        self._fh.flush()

    def tool_result(self, tool_call_idx: int, result: str) -> None:
        self._fh.write(f"\n<<< tool_result #{tool_call_idx}:\n")
        self._fh.write(result.rstrip() + "\n")
        self._fh.flush()

    def final(self, report: str, charts_count: int) -> None:
        self._fh.write("\n========== FINAL REPORT ==========\n")
        self._fh.write(report.rstrip() + "\n")
        self._fh.write(f"\n[charts saved: {charts_count}]\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


Trace = FileTrace | NullTrace
