from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from sqlalchemy import select, func, and_, or_

from app.config import settings
from app.db.session import async_session
from app.models.user import User
from app.models.postback import Postback

router = Router(name=__name__)


# ===== common one-window render =====

async def _set_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        u = await session.get(User, tg_id)
        if not u:
            u = User(id=tg_id)
            session.add(u)
            await session.flush()
        u.last_bot_message_id = message_id
        await session.commit()


async def _render_one(ctx, text: str, kb: InlineKeyboardMarkup):
    if isinstance(ctx, Message):
        chat_id = ctx.chat.id
        user_id = ctx.from_user.id
        bot = ctx.bot
        send = ctx.answer
    else:
        chat_id = ctx.message.chat.id
        user_id = ctx.from_user.id
        bot = ctx.message.bot
        send = ctx.message.answer

    # удалить прошлый экран бота, если был
    last_id = None
    async with async_session() as session:
        u = await session.get(User, user_id)
        if u:
            last_id = u.last_bot_message_id
    if last_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=last_id)
        except Exception:
            pass

    sent = await send(text, reply_markup=kb, disable_web_page_preview=True)
    await _set_last_bot_message_id(user_id, sent.message_id)


# ===== keyboards =====

def kb_stats_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="astats:refresh"),
            InlineKeyboardButton(text="7 дней", callback_data="astats:range:7"),
            InlineKeyboardButton(text="30 дней", callback_data="astats:range:30"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back"),
        ],
    ])


# ===== data aggregation =====

async def _aggregate_stats(days: int = 7) -> str:
    """
    Считает основные метрики:
      - всего пользователей
      - выбрали язык
      - зарегистрированы
      - доступ >= ACCESS (либо депозит не обязателен)
      - VIP
      - сумма депозитов (по users.deposit_total_usd)
      - постбэки за период: всего, регистраций, депозитов, сумма депозитов
    """
    since_ts = int((datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp())

    async with async_session() as session:
        # пользователи — всего
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()

        # выбрали язык (любое непустое)
        chosen_lang = (await session.execute(
            select(func.count()).select_from(User).where(User.lang.isnot(None))
        )).scalar_one()

        # зарегистрированы
        reg_users = (await session.execute(
            select(func.count()).select_from(User).where(User.is_registered.is_(True))
        )).scalar_one()

        # доступ >= ACCESS или депозит не требуется
        if settings.REQUIRE_DEPOSIT:
            access_users = (await session.execute(
                select(func.count()).select_from(User).where(
                    (User.deposit_total_usd >= settings.ACCESS_THRESHOLD_USD)
                )
            )).scalar_one()
        else:
            access_users = total_users  # когда депозит не нужен — у всех доступ

        # VIP
        vip_users = (await session.execute(
            select(func.count()).select_from(User).where(
                or_(
                    User.deposit_total_usd >= settings.VIP_THRESHOLD_USD,
                    User.has_vip.is_(True),
                )
            )
        )).scalar_one()

        # сумма депозитов
        sum_deposits = (await session.execute(
            select(func.coalesce(func.sum(User.deposit_total_usd), 0.0))
        )).scalar_one()
        try:
            sum_deposits = float(sum_deposits or 0.0)
        except Exception:
            sum_deposits = 0.0

        # постбэки за период
        pb_total = (await session.execute(
            select(func.count()).select_from(Postback).where(
                and_(Postback.ts.isnot(None), Postback.ts >= since_ts)
            )
        )).scalar_one()

        pb_reg = (await session.execute(
            select(func.count()).select_from(Postback).where(
                and_(Postback.ts.isnot(None), Postback.ts >= since_ts, Postback.event == "registration")
            )
        )).scalar_one()

        pb_dep_cnt = (await session.execute(
            select(func.count()).select_from(Postback).where(
                and_(
                    Postback.ts.isnot(None), Postback.ts >= since_ts,
                    Postback.event.in_(("deposit_first", "deposit_repeat", "deposit"))
                )
            )
        )).scalar_one()

        pb_dep_sum = (await session.execute(
            select(func.coalesce(func.sum(Postback.amount_usd), 0.0)).where(
                and_(
                    Postback.ts.isnot(None), Postback.ts >= since_ts,
                    Postback.event.in_(("deposit_first", "deposit_repeat", "deposit"))
                )
            )
        )).scalar_one()
        try:
            pb_dep_sum = float(pb_dep_sum or 0.0)
        except Exception:
            pb_dep_sum = 0.0

    # текст
    txt = (
        "<b>📊 Статистика</b>\n\n"
        f"Период: последние <b>{days}</b> дн.\n\n"
        "<b>Пользователи</b>\n"
        f"• Всего: <b>{total_users}</b>\n"
        f"• Выбрали язык: <b>{chosen_lang}</b>\n"
        f"• Зарегистрированы: <b>{reg_users}</b>\n"
        f"• С доступом (ACCESS): <b>{access_users}</b>\n"
        f"• VIP: <b>{vip_users}</b>\n"
        f"• Сумма депозитов (по профилям): <b>${sum_deposits:,.2f}</b>\n\n"
        "<b>Постбэки</b>\n"
        f"• Всего событий: <b>{pb_total}</b>\n"
        f"• Регистрации: <b>{pb_reg}</b>\n"
        f"• Депозиты: <b>{pb_dep_cnt}</b>\n"
        f"• Сумма депозитов: <b>${pb_dep_sum:,.2f}</b>\n"
    )
    return txt


# ===== callbacks =====

@router.callback_query(F.data == "admin:stats")
async def open_stats(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    text = await _aggregate_stats(days=7)
    await _render_one(call, text, kb_stats_root())


@router.callback_query(F.data == "astats:refresh")
async def refresh_stats(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer("Обновлено", show_alert=False)

    text = await _aggregate_stats(days=7)
    await _render_one(call, text, kb_stats_root())


@router.callback_query(F.data.startswith("astats:range:"))
async def range_stats(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    _, _, num = call.data.split(":", 2)
    try:
        days = int(num)
    except Exception:
        days = 7

    await call.answer()
    text = await _aggregate_stats(days=days)
    await _render_one(call, text, kb_stats_root())
