from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, List

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

from sqlalchemy import select, desc

from app.config import settings
from app.db.session import async_session
from app.models.postback import Postback

router = Router(name=__name__)

# ===== in-memory состояние: фильтр + оффсет на пользователя =====
@dataclass
class PBState:
    flt: Literal["all", "reg", "dep"] = "all"
    offset: int = 0

_state: dict[int, PBState] = {}

PAGE = 7  # сколько событий показывать


# ===== helpers =====

def _kb_list(s: PBState) -> InlineKeyboardMarkup:
    row_filters = [
        InlineKeyboardButton(text=("• Все" if s.flt == "all" else "Все"), callback_data="admin:pb:flt:all"),
        InlineKeyboardButton(text=("• Регистрации" if s.flt == "reg" else "Регистрации"), callback_data="admin:pb:flt:reg"),
        InlineKeyboardButton(text=("• Депозиты" if s.flt == "dep" else "Депозиты"), callback_data="admin:pb:flt:dep"),
    ]
    row_nav = [
        InlineKeyboardButton(text="« Пред",    callback_data="admin:pb:nav:prev"),
        InlineKeyboardButton(text="Обновить",  callback_data="admin:pb:refresh"),
        InlineKeyboardButton(text="След »",    callback_data="admin:pb:nav:next"),
    ]
    row_back = [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back")]
    row_cfg  = [InlineKeyboardButton(text="⚙️ Настройка URL постбэка", callback_data="admin:pb:cfg")]

    return InlineKeyboardMarkup(inline_keyboard=[row_filters, row_nav, row_back, row_cfg])


def _safe_ts(pb: Postback) -> str:
    ts = (
        getattr(pb, "created_at", None)
        or getattr(pb, "created", None)
        or getattr(pb, "created_ts", None)
        or getattr(pb, "ts", None)
    )
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    return str(ts) if ts is not None else "-"


def _safe_amount(pb: Postback) -> str:
    val = getattr(pb, "amount_usd", None) or getattr(pb, "amount", None) or getattr(pb, "sumdep", None)
    try:
        return f"${float(val):.2f}"
    except Exception:
        return "-" if val is None else str(val)


def _safe_uid(pb: Postback) -> str:
    return str(getattr(pb, "tg_id", None) or getattr(pb, "user_id", None) or getattr(pb, "uid", None) or "-")


def _fmt_item(pb: Postback) -> str:
    return f"#{pb.id} • {getattr(pb, 'event', '?')} • uid={_safe_uid(pb)} • amount={_safe_amount(pb)} • ts={_safe_ts(pb)}"


def _legend(count: int, offset: int) -> str:
    return (
        "📬 <b>Постбэки — все события</b>\n"
        f"Показано {count} (offset={offset})\n\n"
        "<i>Легенда: id • event • uid • amount • ts</i>\n"
    )


async def _load_items(s: PBState) -> List[Postback]:
    async with async_session() as session:
        q = select(Postback).order_by(desc(Postback.id))
        if s.flt == "reg":
            q = q.where(Postback.event == "registration")
        elif s.flt == "dep":
            q = q.where(Postback.event.in_(("deposit_first", "deposit_repeat", "deposit")))
        q = q.offset(max(s.offset, 0)).limit(PAGE)
        return [row[0] for row in (await session.execute(q)).all()]


async def _render_list(call: CallbackQuery):
    user_id = call.from_user.id
    s = _state.setdefault(user_id, PBState())

    items = await _load_items(s)

    lines = [_legend(len(items), s.offset)]
    for pb in items:
        lines.append(_fmt_item(pb))
    text = "\n".join(lines)

    try:
        await call.message.edit_text(text, reply_markup=_kb_list(s), disable_web_page_preview=True)
    except TelegramBadRequest:
        await call.message.answer(text, reply_markup=_kb_list(s), disable_web_page_preview=True)
    await call.answer()


# ===== публичные входы =====

@router.callback_query(F.data == "admin:postbacks")
async def open_list(call: CallbackQuery):
    _state[call.from_user.id] = PBState()
    await _render_list(call)


@router.callback_query(F.data.startswith("admin:pb:flt:"))
async def set_filter(call: CallbackQuery):
    kind = call.data.split(":", 3)[3]
    s = _state.setdefault(call.from_user.id, PBState())
    s.flt = kind if kind in ("all", "reg", "dep") else "all"
    s.offset = 0
    await _render_list(call)


@router.callback_query(F.data == "admin:pb:nav:prev")
async def nav_prev(call: CallbackQuery):
    s = _state.setdefault(call.from_user.id, PBState())
    s.offset = max(s.offset - PAGE, 0)
    await _render_list(call)


@router.callback_query(F.data == "admin:pb:nav:next")
async def nav_next(call: CallbackQuery):
    s = _state.setdefault(call.from_user.id, PBState())
    s.offset += PAGE
    await _render_list(call)


@router.callback_query(F.data == "admin:pb:refresh")
async def refresh(call: CallbackQuery):
    await _render_list(call)


# ===== экран настройки URL постбэка =====

def _kb_cfg() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:postbacks")]
    ])


def _build_base() -> tuple[str, str, int]:
    host = settings.POSTBACK_HTTP_HOST or "127.0.0.1"
    port = settings.POSTBACK_HTTP_PORT or 8080
    secret = settings.POSTBACK_HTTP_SECRET or "YOUR_SECRET"
    return secret, host, port


def _cfg_text() -> str:
    secret, host, port = _build_base()

    # Только необходимые параметры под каждый тип события
    reg = (
        f"http://{host}:{port}/postback"
        f"?secret={secret}"
        f"&event=registration"
        f"&trader_id={{trader_id}}"
        f"&click_id={{click_id}}"
    )

    dep_first = (
        f"http://{host}:{port}/postback"
        f"?secret={secret}"
        f"&event=deposit_first"
        f"&trader_id={{trader_id}}"
        f"&sumdep={{amount}}"
    )

    dep_repeat = (
        f"http://{host}:{port}/postback"
        f"?secret={secret}"
        f"&event=deposit_repeat"
        f"&trader_id={{trader_id}}"
        f"&sumdep={{amount}}"
    )

    return (
        "⚙️ <b>Настройка URL постбэка</b>\n\n"
        "Скопируйте подходящий URL и подставьте макросы ПП.\n\n"
        "• <b>Регистрация</b>\n"
        f"<code>{reg}</code>\n\n"
        "• <b>Первый депозит</b>\n"
        f"<code>{dep_first}</code>\n\n"
        "• <b>Повторный депозит</b>\n"
        f"<code>{dep_repeat}</code>\n\n"
        "<i>Обязательные макросы:</i>\n"
        "• registration → {trader_id}, {click_id}\n"
        "• deposit_first / deposit_repeat → {trader_id}, {amount}\n"
    )


@router.callback_query(F.data == "admin:pb:cfg")
async def show_cfg(call: CallbackQuery):
    try:
        await call.message.edit_text(_cfg_text(), reply_markup=_kb_cfg(), disable_web_page_preview=True)
    except TelegramBadRequest:
        await call.message.answer(_cfg_text(), reply_markup=_kb_cfg(), disable_web_page_preview=True)
    await call.answer()
