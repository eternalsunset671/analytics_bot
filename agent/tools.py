"""Описание инструментов, которые агент передаёт LLM (function-calling схемы)."""

PYTHON_EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "python_exec",
        "description": (
            "Выполняет Python-код для анализа DataFrame `df`. "
            "Доступны: df (pandas.DataFrame), pd, np, plt. "
            "Печатай результаты через print(). "
            "Для графиков используй plt.figure()/plt.subplots(); не вызывай plt.show() "
            "и не закрывай фигуру — система сама её сохранит. "
            "Запрещено: os/sys/subprocess, open(), чтение/запись файлов, сеть."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python-код для выполнения.",
                }
            },
            "required": ["code"],
        },
    },
}
