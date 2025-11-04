# app/config.py
from __future__ import annotations

from typing import Iterable, List, Optional

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Разрешаем лишние ключи в .env, чтобы не падать при миграциях
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TG / Admin
    BOT_TOKEN: str = Field(default="")
    # Старый формат (один админ) — остаётся для совместимости
    ADMIN_ID: int = Field(default=0)
    # Новый формат (несколько админов) — может быть JSON "[1,2]" или строка "1,2"
    ADMIN_IDS: Optional[str] = Field(default=None)

    POSTBACK_CHANNEL_ID: int = Field(default=0)

    # База (dev: SQLite + aiosqlite). Не удаляй эту строку из .env.
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data.db")

    # Пороги доступа
    ACCESS_THRESHOLD_USD: float = 100.0
    VIP_THRESHOLD_USD: float = 300.0

    # Флаги шагов
    REQUIRE_SUBSCRIPTION: bool = True
    REQUIRE_DEPOSIT: bool = True

    # Подписка — один канал (или None)
    SUB_CHANNEL_ID: int | None = None

    # Ссылки
    REF_LINK: str = Field(default="")
    MINIAPP_LINK_REGULAR: str = Field(default="https://example.com/regular")
    MINIAPP_LINK_VIP: str = Field(default="https://example.com/vip")

    # Поддержка / хаб подписки
    SUPPORT_URL: str = Field(default="https://t.me/")
    SUB_CHANNELS_URL: str = Field(default="https://t.me/")

    # Необязательный лог-канал для карточек постбэков
    LOG_CHANNEL_ID: int | None = None

    # HTTP-приёмник постбэков (aiohttp)
    POSTBACK_HTTP_HOST: str = Field(default="0.0.0.0")
    POSTBACK_HTTP_PORT: int = Field(default=8080)
    POSTBACK_HTTP_SECRET: str | None = None

    # --- Удобные хелперы ---

    def sub_channel_id(self) -> int | None:
        try:
            return int(self.SUB_CHANNEL_ID) if self.SUB_CHANNEL_ID is not None else None
        except Exception:
            return None

    def admin_ids(self) -> List[int]:
        """
        Возвращает список админов, собранный из ADMIN_IDS (JSON или "1,2,3")
        и/или одиночного ADMIN_ID. Дубликаты удаляются.
        """
        ids: list[int] = []
        # 1) массив в ADMIN_IDS
        raw = (self.ADMIN_IDS or "").strip()
        if raw:
            # пробуем JSON
            try:
                import json
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    ids.extend(int(x) for x in parsed)
                else:
                    # если вдруг не список — пробуем как csv
                    raise ValueError
            except Exception:
                # csv через запятую/пробелы
                parts = [p for p in raw.replace(";", ",").split(",") if p.strip()]
                ids.extend(int(p.strip()) for p in parts)
        # 2) одиночный ADMIN_ID (старый формат)
        try:
            if int(self.ADMIN_ID) > 0:
                ids.append(int(self.ADMIN_ID))
        except Exception:
            pass

        # Удаляем дубли и нули
        uniq = sorted({i for i in ids if isinstance(i, int) and i > 0})
        return uniq

    def is_admin(self, uid: int | str) -> bool:
        try:
            val = int(uid)
        except Exception:
            return False
        return val in self.admin_ids()


settings = Settings()
