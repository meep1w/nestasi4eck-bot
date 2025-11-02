from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TG / Admin
    BOT_TOKEN: str = Field(default="")
    ADMIN_ID: int = Field(default=0)
    POSTBACK_CHANNEL_ID: int = Field(default=0)

    # База (dev: SQLite + aiosqlite)
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data.db")

    # Пороги доступа
    ACCESS_THRESHOLD_USD: float = 100.0
    VIP_THRESHOLD_USD: float = 300.0

    # Флаги шагов
    REQUIRE_SUBSCRIPTION: bool = True
    REQUIRE_DEPOSIT: bool = True
    # Регистрацию не отключаем — это константа в логике

    # Подписка — ТЕПЕРЬ ТОЛЬКО ОДИН КАНАЛ
    # Пример в .env: SUB_CHANNEL_ID=-1001234567890
    SUB_CHANNEL_ID: int | None = None

    # Ссылки
    REF_LINK: str = Field(default="")
    MINIAPP_LINK_REGULAR: str = Field(default="https://example.com/regular")
    MINIAPP_LINK_VIP: str = Field(default="https://example.com/vip")

    # ВАЖНО: ссылки на поддержку и «хаб» подписки
    SUPPORT_URL: str = Field(default="https://t.me/")      # «🛟 Поддержка»
    SUB_CHANNELS_URL: str = Field(default="https://t.me/") # «📨 Подписаться» (может вести прямо на канал)

    # Необязательный лог-канал для карточек постбэков
    LOG_CHANNEL_ID: int | None = None

    # HTTP-приёмник постбэков (aiohttp)
    POSTBACK_HTTP_HOST: str = Field(default="0.0.0.0")
    POSTBACK_HTTP_PORT: int = Field(default=8080)
    POSTBACK_HTTP_SECRET: str | None = None  # если задан, ожидаем &secret=... в запросе

    # Хелпер: один канал подписки или None
    def sub_channel_id(self) -> int | None:
        try:
            return int(self.SUB_CHANNEL_ID) if self.SUB_CHANNEL_ID is not None else None
        except Exception:
            return None


settings = Settings()
