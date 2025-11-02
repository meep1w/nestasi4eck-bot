from __future__ import annotations

from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from sqlalchemy import select, desc, or_

from app.config import settings
from app.db.session import async_session
from app.models.user import User
from app.models.postback import Postback

router = Router(name=__name__)

PAGE_SIZE = 10
EVENT_FILTERS = ("all", "registration", "deposit")  # deposit = deposit_first|deposit_repeat|deposit


# ===== low-level render helpers =====

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


# ===== ui =====

def _kb_filters(active: str, offset: int) -> InlineKeyboardMarkup:
    def chip(title: str, val: str) -> InlineKeyboardButton:
        mark = "• " if val == active else ""
        return InlineKeyboardButton(text=f"{mark}{title}", callback_data=f"apb:list:{val}:{offset}")

    rows = [
        [
            chip("Все", "all"),
            chip("Регистрации", "registration"),
            chip("Депозиты", "deposit"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _kb_pager(active: str, offset: int, total: int) -> InlineKeyboardMarkup:
    prev_off = max(offset - PAGE_SIZE, 0)
    next_off = offset + PAGE_SIZE if (offset + PAGE_SIZE) < total else offset
    rows = [
        [
            InlineKeyboardButton(text="« Пред", callback_data=f"apb:list:{active}:{prev_off}"),
            InlineKeyboardButton(text="Обновить", callback_data=f"apb:list:{active}:{offset}"),
            InlineKeyboardButton(text="След »", callback_data=f"apb:list:{active}:{next_off}"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_item(pb: Postback) -> str:
    ev = pb.event or "—"
    uid = pb.tg_id if pb.tg_id is not None else "—"
    amt = f"${pb.amount_usd:.2f}" if pb.amount_usd is not None else "—"
    ts = pb.ts or 0
    return f"#{pb.id} • <b>{ev}</b> • uid=<code>{uid}</code> • amount={amt} • ts={ts}"


def _format_list(title: str, items: list[Postback], offset: int, total: int) -> str:
    lines = "\n".join(_format_item(pb) for pb in items) or "—"
    head = f"<b>📨 Постбэки</b> — {title}\nПоказано {len(items)} из {total} (offset={offset})\n\n"
    legend = "Легенда: id • event • uid • amount • ts\n\n"
    return head + legend + lines


# ===== data queries =====

async def _query_postbacks(filter_key: str, offset: int) -> tuple[list[Postback], int]:
    """
    Возвращает (items, total_count) по фильтру и оффсету.
    filter_key: all | registration | deposit
    """
    async with async_session() as session:
        base = select(Postback).order_by(desc(Postback.id))

        if filter_key == "registration":
            where = base.where(Postback.event == "registration")
        elif filter_key == "deposit":
            where = base.where(Postback.event.in_(("deposit_first", "deposit_repeat", "deposit")))
        else:
            where = base

        # total
        total = (await session.execute(where.with_only_columns(Postback.id))).all()
        total_count = len(total)

        # page slice (SQLite без LIMIT/OFFSET через ORM — делаем руками)
        ids = [row[0] for row in total]
        page_ids = ids[offset: offset + PAGE_SIZE]
        if not page_ids:
            return [], total_count

        page = (await session.execute(
            select(Postback).where(Postback.id.in_(page_ids)).order_by(desc(Postback.id))
        )).scalars().all()
        return page, total_count


# ===== entry & callbacks =====

@router.callback_query(F.data == "admin:postbacks")
async def open_postbacks(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    items, total = await _query_postbacks("all", 0)
    text = _format_list("все события", items, 0, total)
    # две клавы: сверху фильтры, снизу пагинация
    top = _kb_filters("all", 0)
    bottom = _kb_pager("all", 0, total)

    # слепим обе (aiogram 3 не поддерживает «две клавы», поэтому добавим ряды вместе)
    kb = InlineKeyboardMarkup(inline_keyboard=top.inline_keyboard + bottom.inline_keyboard)
    await _render_one(call, text, kb)


@router.callback_query(F.data.startswith("apb:list:"))
async def list_postbacks(call: CallbackQuery):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    _, _, filter_key, offset_str = call.data.split(":", 3)
    if filter_key not in EVENT_FILTERS:
        filter_key = "all"
    try:
        offset = max(int(offset_str), 0)
    except Exception:
        offset = 0

    items, total = await _query_postbacks(filter_key, offset)
    title = "все события" if filter_key == "all" else ("регистрации" if filter_key == "registration" else "депозиты")
    text = _format_list(title, items, offset, total)

    top = _kb_filters(filter_key, offset)
    bottom = _kb_pager(filter_key, offset, total)
    kb = InlineKeyboardMarkup(inline_keyboard=top.inline_keyboard + bottom.inline_keyboard)

    await call.answer()
    await _render_one(call, text, kb)
