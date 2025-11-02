from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Boolean, DateTime

from .base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Профиль/настройки
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ref_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Прохождение шагов
    is_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    deposit_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    has_vip: Mapped[bool] = mapped_column(Boolean, default=False)
    is_subscribed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Одноразовые экраны
    shown_regular_access_once: Mapped[bool] = mapped_column(Boolean, default=False)
    shown_vip_access_once: Mapped[bool] = mapped_column(Boolean, default=False)

    # UI
    last_bot_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Связка с партнёркой
    click_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    partner_trader_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)

    # Служебное
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return (f"<User id={self.id} reg={self.is_registered} dep={self.deposit_total_usd} vip={self.has_vip} "
                f"click={self.click_id} trader={self.partner_trader_id} "
                f"shown_ok={self.shown_regular_access_once} shown_vip={self.shown_vip_access_once}>")
