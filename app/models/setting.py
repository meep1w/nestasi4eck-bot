from typing import Optional

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Setting(Base):
    """
    Простейшее key-value хранилище для гибких настроек в админке.
    Поддерживаем строковые, числовые и булевы значения — одно из трёх полей используется.
    """
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)

    value_str: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    value_float: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_bool: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
