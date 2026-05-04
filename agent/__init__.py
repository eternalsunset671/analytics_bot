"""ИИ-агент, анализирующий DataFrame через python_exec (tool use)."""

from agent.core import MAX_ITERATIONS, run_agent
from agent.injection import MAX_INSTRUCTION_LEN, sanitize_instruction

__all__ = [
    "MAX_INSTRUCTION_LEN",
    "MAX_ITERATIONS",
    "run_agent",
    "sanitize_instruction",
]
