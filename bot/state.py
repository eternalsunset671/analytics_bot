"""Хранилище загруженных пользователями файлов и доступ к демо-датасету."""

from __future__ import annotations

import os

from data.loader import load_file

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DEMO_FILE = os.path.join(_PROJECT_ROOT, "demo.csv")

# chat_id → путь к временно сохранённому пользовательскому файлу
user_files: dict[int, str] = {}


def get_df(chat_id: int):
    """Возвращает (DataFrame, is_demo) или (None, False), если ничего не доступно."""
    path = user_files.get(chat_id)
    if path and os.path.exists(path):
        return load_file(path), False
    if os.path.exists(DEMO_FILE):
        return load_file(DEMO_FILE), True
    return None, False


def forget_user_file(chat_id: int) -> None:
    """Удаляет ссылку на файл пользователя и сам tmp-файл, если он есть."""
    path = user_files.pop(chat_id, None)
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


def remember_user_file(chat_id: int, path: str) -> None:
    """Сохраняет путь к новому файлу пользователя, удаляя предыдущий."""
    forget_user_file(chat_id)
    user_files[chat_id] = path
