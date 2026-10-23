"""Настройки приложения, читаемые из переменных окружения и файла .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация сервиса.

    Поддерживаются два взаимно исключающих способа задать подключение к БД:

    * ``DATABASE_URL`` — готовая строка подключения (имеет приоритет);
    * ``PGHOST`` / ``PGPORT`` / ``PGDATABASE`` / ``PGUSER`` / ``PGPASSWORD``.

    Имена переменных регистронезависимы (``PGHOST`` == ``pghost``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # HTTP-сервер
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # CORS: список origins через запятую
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # PostgreSQL: вариант 1 — единая строка подключения
    database_url: str | None = None

    # PostgreSQL: вариант 2 — разрозненные параметры
    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str = "alfa-hakaton"
    pguser: str = "postgres"
    pgpassword: str = "postgres"

    @property
    def cors_origin_list(self) -> list[str]:
        """Разбирает ``CORS_ORIGINS`` в список, отбрасывая пустые элементы."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def connect_kwargs(self) -> dict[str, Any]:
        """Аргументы для ``psycopg.connect`` с таймаутом установки соединения."""
        if self.database_url:
            return {"conninfo": self.database_url, "connect_timeout": 5}

        kwargs: dict[str, Any] = {
            "host": self.pghost,
            "port": self.pgport,
            "dbname": self.pgdatabase,
            "user": self.pguser,
            "connect_timeout": 5,
        }
        if self.pgpassword:
            kwargs["password"] = self.pgpassword
        return kwargs


@lru_cache
def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэшируется на процесс)."""
    return Settings()
