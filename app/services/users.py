from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.config import settings
from app.models.user import User


Step = Literal[
    "subscription",     # показать экран проверки подписки
    "registration",     # показать экран проверки регистрации
    "deposit",          # показать экран проверки депозита
    "access_ok_once",   # одноразовое окно «Доступ открыт» (обычный)
    "vip_once",         # одноразовое окно «VIP доступ»
    "open_regular",     # сразу открывать мини-апп (обычная)
    "open_vip",         # сразу открывать мини-апп (VIP)
]


@dataclass
class AccessDecision:
    """
    Результат вычисления следующего шага.
    """
    step: Step
    vip: bool = False                 # актуально для open_* и *_once
    need_amount: float = 0.0          # сколько нужно по порогу (для экрана депозита)
    have_amount: float = 0.0          # сколько уже есть (для экрана депозита)


def _has_regular_access(u: User) -> bool:
    return (u.deposit_total_usd or 0.0) >= settings.ACCESS_THRESHOLD_USD or not settings.REQUIRE_DEPOSIT


def _has_vip_access(u: User) -> bool:
    return (u.deposit_total_usd or 0.0) >= settings.VIP_THRESHOLD_USD


def decide_next_step(u: User) -> AccessDecision:
    """
    Центральная логика принятия решения о следующем шаге доступа.

    Порядок (как ты попросил):
    1) Подписка (если включена)
    2) Регистрация (обязательна)
    3) Депозит (если включён) -> обычный или VIP доступ

    Возвращает одно из:
      - "subscription" / "registration" / "deposit" (если нужно показать соответствующий экран)
      - "access_ok_once" (если обычный доступ впервые — показать одноразовое окно)
      - "vip_once" (если VIP доступ впервые — показать одноразовое окно)
      - "open_regular" / "open_vip" (если одноразовые окна уже показаны — сразу открывать мини-апп)
    """
    # 1) Подписка
    if settings.REQUIRE_SUBSCRIPTION and not (u.is_subscribed or False):
        return AccessDecision(step="subscription")

    # 2) Регистрация (нельзя отключить)
    if not (u.is_registered or False):
        return AccessDecision(step="registration")

    # 3) Депозит
    if settings.REQUIRE_DEPOSIT:
        total = float(u.deposit_total_usd or 0.0)

        # VIP приоритетнее
        if total >= settings.VIP_THRESHOLD_USD or (u.has_vip or False):
            # уже VIP; решаем, показывали ли одноразовое окно
            if not (u.shown_vip_access_once or False):
                return AccessDecision(step="vip_once", vip=True)
            # окно уже показывали — открываем мини-апп
            return AccessDecision(step="open_vip", vip=True)

        # Обычный доступ
        if total >= settings.ACCESS_THRESHOLD_USD:
            if not (u.shown_regular_access_once or False):
                return AccessDecision(step="access_ok_once", vip=False)
            return AccessDecision(step="open_regular", vip=False)

        # Недобор — показать экран депозита с цифрами
        need = max(settings.ACCESS_THRESHOLD_USD - total, 0.0)
        return AccessDecision(step="deposit", need_amount=need, have_amount=total)

    # Если депозит не требуется:
    # Если пользователь уже VIP по сумме (мог быть ранее или пришёл постбэк)
    if _has_vip_access(u) or (u.has_vip or False):
        if not (u.shown_vip_access_once or False):
            return AccessDecision(step="vip_once", vip=True)
        return AccessDecision(step="open_vip", vip=True)

    # Иначе — обычный доступ без депозита
    if not (u.shown_regular_access_once or False):
        return AccessDecision(step="access_ok_once", vip=False)
    return AccessDecision(step="open_regular", vip=False)


# Удобные хелперы для обновления одноразовых флагов
def mark_regular_once_shown(u: User) -> None:
    u.shown_regular_access_once = True


def mark_vip_once_shown(u: User) -> None:
    u.shown_vip_access_once = True
