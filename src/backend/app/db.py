"""Работа с PostgreSQL через psycopg 3.

Соединения короткоживущие: на каждый запрос открывается новое подключение
(пул для минимального backend не нужен). Все эндпоинты синхронные, поэтому
FastAPI выполняет их в threadpool и не блокирует event loop.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from .config import get_settings

logger = logging.getLogger(__name__)


def get_connection() -> psycopg.Connection[Any]:
    """Открывает новое подключение к БД. Может бросить ``psycopg.Error``."""
    return psycopg.connect(**get_settings().connect_kwargs)


@contextmanager
def connection() -> Iterator[psycopg.Connection[Any]]:
    """Контекстный менеджер подключения: гарантированно закрывает соединение."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def ping() -> bool:
    """Проверяет доступность БД запросом ``SELECT 1``.

    Никогда не бросает исключение: при любой ошибке пишет её в лог
    и возвращает ``False``.
    """
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    except (psycopg.Error, OSError) as exc:
        logger.warning("Проверка доступности БД не удалась: %s", exc)
        return False
