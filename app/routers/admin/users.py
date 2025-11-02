# app/routers/admin/users.py
from __future__ import annotations

from typing import Optional, List, Tuple

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from sqlalchemy import select, func, desc, or_, and_

from app.config import settings
from app.db.session import async_session
from app.models.user import User

router = Router(name=__name__)

# --- helpers: one-screen rendering (без спама) ---
async def _set_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        u = await session.get(User, tg_id)
        if not u:
            u = User(id=tg_id)
            session.add(u)
            await session.flush()
        u.last_bot_message_id = message_id
        await session.commit()

async def _render_one(ctx, text: str, kb: InlineKeyboardMarkup, disable_preview: bool = True):
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

    sent = await send(text, reply_markup=kb, disable_web_page_preview=disable_preview)
    await _set_last_bot_message_id(user_id, sent.message_id)

# --- counters ---
async def _get_counters() -> Tuple[int, int, int, int, int, float]:
    async with async_session() as session:
        total = (await session.execute(select(func.count()).select_from(User))).scalar_one()

        registered = (await session.execute(
            select(func.count()).select_from(User).where(User.is_registered.is_(True))
        )).scalar_one()

        if settings.REQUIRE_DEPOSIT:
            access_ok = (await session.execute(
                select(func.count()).select_from(User).where(User.deposit_total_usd >= settings.ACCESS_THRESHOLD_USD)
            )).scalar_one()
        else:
            access_ok = total

        vip = (await session.execute(
            select(func.count()).select_from(User).where(
                or_(User.has_vip.is_(True), User.deposit_total_usd >= settings.VIP_THRESHOLD_USD)
            )
        )).scalar_one()

        subscribed = (await session.execute(
            select(func.count()).select_from(User).where(User.is_subscribed.is_(True))
        )).scalar_one()

        dep_sum = float((await session.execute(
            select(func.coalesce(func.sum(User.deposit_total_usd), 0.0))
        )).scalar_one() or 0.0)

        return total, registered, access_ok, vip, subscribed, dep_sum

def _fmt_header() -> str:
    return "👥 <b>Пользователи</b>\n\n"

# --- keyboards ---
def _kb_users_list(users: List[User], page: int) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append([InlineKeyboardButton(text="🔍 Поиск", callback_data="users:search")])
    buf: List[InlineKeyboardButton] = []
    for u in users:
        short = f"{u.id} • {(u.lang or '-').upper() if u.lang else '-'}"
        if (u.deposit_total_usd or 0) > 0:
            short += f" • ${int(u.deposit_total_usd)}"
        if u.has_vip or (u.deposit_total_usd or 0) >= settings.VIP_THRESHOLD_USD:
            short += " 👑"
        buf.append(InlineKeyboardButton(text=short, callback_data=f"users:open:{u.id}:{page}"))
        if len(buf) == 2:
            rows.append(buf); buf = []
    if buf:
        rows.append(buf)

    nav: List[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"users:page:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}", callback_data="users:noop"))
    nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"users:page:{page+1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 В меню", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def _kb_back_to_list(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К списку", callback_data=f"users:page:{page}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="admin:back")],
    ])

# --- data access ---
async def _get_users_page(page: int, per_page: int = 10) -> List[User]:
    offset = max(0, (page - 1) * per_page)
    async with async_session() as session:
        q = select(User).order_by(desc(User.created_at)).offset(offset).limit(per_page)
        rows = (await session.execute(q)).scalars().all()
        return list(rows)

# --- search helpers ---
async def _find_user_by_query(query: str, bot) -> Optional[User]:
    q = query.strip()
    async with async_session() as session:
        if q.lstrip("-").isdigit():
            user = await session.get(User, int(q))
            if user:
                return user
        row = (await session.execute(select(User).where(User.click_id == q))).scalars().first()
        if row:
            return row
        row = (await session.execute(select(User).where(User.partner_trader_id == q))).scalars().first()
        if row:
            return row
    try:
        if q.startswith("@"):
            chat = await bot.get_chat(q)
            if chat and chat.id:
                async with async_session() as session:
                    return await session.get(User, int(chat.id))
    except Exception:
        pass
    return None

# --- open entrypoint ---
@router.callback_query(F.data == "admin:users")
async def open_users(call: CallbackQuery):
    total, reg, access_ok, vip, sub, dep_sum = await _get_counters()
    page = 1
    users = await _get_users_page(page)
    text = (
        _fmt_header() +
        f"Всего: <b>{total}</b>\n"
        f"Регистрация: <b>{reg}</b>\n"
        f"Доступ (>= ACCESS): <b>{access_ok}</b>\n"
        f"VIP: <b>{vip}</b>\n"
        f"Подписка: <b>{sub}</b>\n"
        f"Сумма депозитов: <b>${int(dep_sum)}</b>\n\n"
        "Выберите пользователя или воспользуйтесь поиском."
    )
    await _render_one(call, text, _kb_users_list(users, page))
    await call.answer()

@router.callback_query(F.data.startswith("users:page:"))
async def paginate(call: CallbackQuery):
    page = int(call.data.split(":")[2])
    total, reg, access_ok, vip, sub, dep_sum = await _get_counters()
    users = await _get_users_page(page)
    if not users and page > 1:
        page -= 1
        users = await _get_users_page(page)
    text = (
        _fmt_header() +
        f"Всего: <b>{total}</b> • Рег: <b>{reg}</b> • Доступ: <b>{access_ok}</b> • VIP: <b>{vip}</b> • Подписка: <b>{sub}</b>\n"
        f"Сумма депозитов: <b>${int(dep_sum)}</b>\n\n"
        "Выберите пользователя или воспользуйтесь поиском."
    )
    await _render_one(call, text, _kb_users_list(users, page))
    await call.answer()

# --- search flow ---
_pending_search: set[int] = set()

@router.callback_query(F.data == "users:search")
async def search_prompt(call: CallbackQuery):
    _pending_search.add(call.from_user.id)
    await call.message.answer(
        "🔎 Отправьте <b>trader_id</b> или <b>click_id</b> или <b>tg_id</b> или <b>@username</b>.",
        disable_web_page_preview=True
    )
    await call.answer()

@router.message(F.text)
async def search_catcher(m: Message):
    if m.from_user.id not in _pending_search:
        return
    _pending_search.discard(m.from_user.id)

    q = (m.text or "").strip()
    user = await _find_user_by_query(q, m.bot)
    if not user:
        await m.answer("Ничего не найдено. Попробуйте другой идентификатор.")
        return

    await _show_user_card(m, user, page=1)

# --- user card ---
def _fmt_user_card(u: User) -> str:
    dep = float(u.deposit_total_usd or 0)
    vip = bool(u.has_vip) or dep >= settings.VIP_THRESHOLD_USD
    shown_access = bool(getattr(u, "shown_regular_access_once", False))
    shown_vip = bool(getattr(u, "shown_vip_access_once", False))
    created = getattr(u, "created_at", None)
    updated = getattr(u, "updated_at", None)
    return (
        "🧾 <b>Пользователь</b>\n\n"
        f"• TG ID: <code>{u.id}</code>\n"
        f"• Язык: <b>{(u.lang or '-').upper()}</b>\n"
        f"• Реф-код: <code>{u.ref_code or '—'}</code>\n"
        f"• click_id: <code>{u.click_id or '—'}</code>\n"
        f"• trader_id: <code>{u.partner_trader_id or '—'}</code>\n"
        f"• Регистрация: <b>{'да' if u.is_registered else 'нет'}</b>\n"
        f"• Подписка: <b>{'да' if u.is_subscribed else 'нет'}</b>\n"
        f"• Депозит всего: <b>${int(dep)}</b>\n"
        f"• VIP: <b>{'да' if vip else 'нет'}</b>\n"
        f"• Показан «Доступ открыт»: <b>{'да' if shown_access else 'нет'}</b>\n"
        f"• Показан «VIP доступ»: <b>{'да' if shown_vip else 'нет'}</b>\n"
        f"• Создан: <code>{str(created) if created else '—'}</code>\n"
        f"• Обновлён: <code>{str(updated) if updated else '—'}</code>\n"
    )

async def _show_user_card(ctx, u: User, page: int):
    kb = _kb_back_to_list(page)
    await _render_one(ctx, _fmt_user_card(u), kb)

@router.callback_query(F.data.startswith("users:open:"))
async def open_user_card(call: CallbackQuery):
    _, _, uid, page = call.data.split(":")
    async with async_session() as session:
        u = await session.get(User, int(uid))
    if not u:
        await call.answer("Пользователь не найден.", show_alert=True)
        return
    await _show_user_card(call, u, page=int(page))
    await call.answer()

@router.callback_query(F.data == "users:noop")
async def noop(call: CallbackQuery):
    await call.answer()
