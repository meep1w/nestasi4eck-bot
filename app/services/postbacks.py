from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.user import User
from app.models.postback import Postback


@dataclass
class ApplyResult:
    id: int
    event: str
    tg_id: Optional[int]
    trader_id: Optional[str]
    click_id: Optional[str]
    amount_usd: float
    total_after: float
    is_registered: bool
    became_vip: bool


async def _find_user_for_postback_ids(
    tg_id: Optional[int],
    trader_id: Optional[str],
    click_id: Optional[str],
) -> Optional[int]:
    """
    Возвращает user_id (tg) если нашли пользователя по tg_id / trader_id / click_id.
    """
    async with async_session() as session:
        if tg_id:
            u = await session.get(User, tg_id)
            if u:
                return u.id

        if trader_id:
            q = select(User.id).where(User.partner_trader_id == str(trader_id))
            uid = (await session.execute(q)).scalar_one_or_none()
            if uid:
                return uid

        if click_id:
            q = select(User.id).where(User.click_id == str(click_id))
            uid = (await session.execute(q)).scalar_one_or_none()
            if uid:
                return uid

        return None


async def apply_postback(payload: dict) -> ApplyResult:
    """
    payload:
      event: registration|deposit_first|deposit_repeat|deposit
      tg_id: Optional[int]
      trader_id: Optional[str]
      click_id: Optional[str]
      amount_usd: Optional[float]
      ts: Optional[int]
      raw_text: str
    """
    event = (payload.get("event") or "").lower()
    tg_id = payload.get("tg_id")
    trader_id = payload.get("trader_id")
    click_id = payload.get("click_id")
    amount = float(payload.get("amount_usd") or 0.0)

    # 1) Сохраняем сырой постбэк
    async with async_session() as session:
        pb = Postback(
            event=event,
            tg_id=tg_id,
            external_id=payload.get("external_id"),
            amount_usd=amount,
            raw_text=payload.get("raw_text") or "",
        )
        session.add(pb)
        await session.flush()
        pb_id = pb.id
        await session.commit()

    # 2) Ищем/создаём пользователя — В ЭТОЙ ЖЕ СЕССИИ, где будем апдейтить!
    async with async_session() as session:
        # узнаём id пользователя по любому из идентификаторов
        uid = await _find_user_for_postback_ids(tg_id, trader_id, click_id)

        u: Optional[User] = None
        if uid:
            u = await session.get(User, uid)
        elif tg_id:
            # если не нашли, но знаем tg_id — создадим пустого
            u = await session.get(User, tg_id)
            if not u:
                u = User(id=tg_id)
                session.add(u)
                await session.flush()

        became_vip = False

        # 3) Применяем событие
        if u:
            if event == "registration":
                u.is_registered = True
                if trader_id and not u.partner_trader_id:
                    u.partner_trader_id = str(trader_id)
                if click_id and not u.click_id:
                    u.click_id = str(click_id)

            if event in {"deposit_first", "deposit_repeat", "deposit"}:
                if amount and amount > 0:
                    u.deposit_total_usd = float((u.deposit_total_usd or 0.0) + amount)
                if trader_id and not u.partner_trader_id:
                    u.partner_trader_id = str(trader_id)
                if (u.deposit_total_usd or 0.0) >= settings.VIP_THRESHOLD_USD and not u.has_vip:
                    u.has_vip = True
                    became_vip = True

            await session.commit()
            await session.refresh(u)

            return ApplyResult(
                id=pb_id,
                event=event,
                tg_id=u.id,
                trader_id=u.partner_trader_id,
                click_id=u.click_id,
                amount_usd=amount,
                total_after=u.deposit_total_usd or 0.0,
                is_registered=bool(u.is_registered),
                became_vip=became_vip,
            )

        # Если пользователя так и нет (например, пришёл только чужой click_id без tg_id)
        return ApplyResult(
            id=pb_id,
            event=event,
            tg_id=tg_id,
            trader_id=str(trader_id) if trader_id else None,
            click_id=str(click_id) if click_id else None,
            amount_usd=amount,
            total_after=0.0,
            is_registered=False,
            became_vip=False,
        )


async def recompute_user_from_postbacks(tg_id: int) -> User:
    # Сейчас агрегаты уже пишем напрямую в User в apply_postback.
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def send_postback_card(bot: Bot, res: ApplyResult):
    title = {
        "registration": "Registration",
        "deposit_first": "First deposit",
        "deposit_repeat": "Repeat deposit",
        "deposit": "Deposit",
    }.get(res.event, res.event)

    lines = [
        f"<b>{title}</b>",
        f"User: <code>{res.tg_id or '-'}</code>",
        f"Trader ID: <code>{res.trader_id or '-'}</code>",
        f"Click ID: <code>{res.click_id or '-'}</code>",
    ]
    if res.amount_usd:
        lines.append(f"Amount: <b>${res.amount_usd:.2f}</b>")
    if res.total_after:
        lines.append(f"Total: <b>${res.total_after:.2f}</b>")

    if res.became_vip:
        lines.append("Status: 👑 <b>VIP</b>")

    text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="#pb_" + str(res.id), url="https://t.me/")],
    ])

    try:
        await bot.send_message(
            chat_id=settings.POSTBACK_CHANNEL_ID,
            text=text,
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    except Exception:
        pass
