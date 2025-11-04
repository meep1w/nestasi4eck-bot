# app/config.py
from __future__ import annotations

from typing import List, Optional, Iterable

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === Telegram ===
    BOT_TOKEN: str

    # === Admins ===
    # Новый способ: список админов (через запятую)
    ADMIN_IDS: List[int] = Field(default_factory=list)
    # Старый способ: один админ (оставлен для обратной совместимости)
    ADMIN_ID: Optional[int] = None

    # === Access flow flags ===
    REQUIRE_SUBSCRIPTION: bool = True
    REQUIRE_DEPOSIT: bool = True

    # === Channels / subscription ===
    # один ID канала (int, со знаком минус для каналов)
    SUB_CHANNEL_ID: Optional[int] = None
    # или несколько id через запятую
    SUB_CHANNEL_IDS: Optional[str] = None
    SUB_CHANNELS_URL: str = "https://t.me/"

    # === Thresholds (USD) ===
    ACCESS_THRESHOLD_USD: float = 50.0
    VIP_THRESHOLD_USD: float = 300.0

    # === Links ===
    REF_LINK: str = "https://example.com"
    MINIAPP_LINK_REGULAR: str = "https://your-gh-pages/regular"
    MINIAPP_LINK_VIP: str = "https://your-gh-pages/vip"
    SUPPORT_URL: str = "https://t.me/"

    # === Postback HTTP receiver ===
    POSTBACK_HTTP_HOST: str = "0.0.0.0"
    POSTBACK_HTTP_PORT: int = 8080
    POSTBACK_HTTP_SECRET: str = "YOUR_SECRET"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v):

        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple)):
            return [int(x) for x in v]
        return [int(x.strip()) for x in str(v).split(",") if x.strip()]

    @model_validator(mode="after")
    def _normalize_admins(self):

        ids = set(self.ADMIN_IDS or [])
        if self.ADMIN_ID:
            ids.add(int(self.ADMIN_ID))
        self.ADMIN_IDS = sorted(ids)
        return self

    # ---- helpers for codebase ----
    def is_admin(self, uid: int) -> bool:
        try:
            return int(uid) in self.ADMIN_IDS
        except Exception:
            return False

    def sub_channel_id(self) -> Optional[int]:
        return self.SUB_CHANNEL_ID

    def sub_channel_ids_list(self) -> Iterable[int]:

        if self.SUB_CHANNEL_IDS:
            return [int(x.strip()) for x in self.SUB_CHANNEL_IDS.split(",") if x.strip()]
        if self.SUB_CHANNEL_ID is not None:
            return [int(self.SUB_CHANNEL_ID)]
        return []


settings = Settings()
