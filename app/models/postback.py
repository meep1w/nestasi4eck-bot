from typing import Optional

from sqlalchemy import BigInteger, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Postback(Base):
    __tablename__ = "postbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Тип события: 'registration' | 'deposit'
    event: Mapped[str] = mapped_column(String(32))

    # Связка с пользователем (если известен)
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Внешний идентификатор (если постбэк шлёт не tg_id)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Для депозитов
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Временная метка события (unix)
    ts: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Оригинальный текст сообщения из канала постбэков
    raw_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Хеш для идемпотентности
    hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)


# Индексы для быстрого поиска
Index("ix_postbacks_event", Postback.event)
Index("ix_postbacks_tg_id", Postback.tg_id)
Index("ix_postbacks_ts", Postback.ts)
