from __future__ import annotations

from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    FSInputFile,
)

from app.config import settings
from app.db.session import async_session
from app.models.user import User

router = Router(name=__name__)
IMG_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"


# ===== DB helpers =====
async def _get_user(tg_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.get(User, tg_id)


async def _set_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        u = await session.get(User, tg_id)
        if not u:
            return
        u.last_bot_message_id = message_id
        await session.commit()


# ===== MAIN MENU RENDER =====
async def render_main_menu(m: Message, lang: str, vip: Optional[bool] = None):
    """
    Раскладка:
    [📘 Инструкция]
    [🛟 Поддержка] [🌐 Сменить язык]
    [📡 Получить сигнал]  (или 👑 VIP сигналы как WebApp при открытом доступе)
    """
    u = await _get_user(m.from_user.id)
    deposit = float((u.deposit_total_usd or 0.0) if u else 0.0)
    access_open = (not settings.REQUIRE_DEPOSIT) or (deposit >= settings.ACCESS_THRESHOLD_USD)
    is_vip = bool(getattr(u, "has_vip", False) or deposit >= settings.VIP_THRESHOLD_USD)

    title = "<b>Главное меню</b>"

    # --- клавиатура (новая раскладка) ---
    rows = []

    # 1) Инструкция — отдельной строкой
    rows.append([InlineKeyboardButton(text="📘 Инструкция", callback_data="go:instruction")])

    # 2) Поддержка + Сменить язык — в один ряд
    rows.append([
        InlineKeyboardButton(text="🛟 Поддержка", url=settings.SUPPORT_URL),
        InlineKeyboardButton(text="🌐 Сменить язык", callback_data="go:lang"),
    ])

    # 3) Получить сигнал / VIP сигналы — отдельной строкой внизу
    if access_open or is_vip or vip:
        url = settings.MINIAPP_LINK_VIP if (is_vip or vip) else settings.MINIAPP_LINK_REGULAR
        rows.append([
            InlineKeyboardButton(
                text=("👑 VIP сигналы" if (is_vip or vip) else "📡 Получить сигнал"),
                web_app=WebAppInfo(url=url)
            )
        ])
    else:
        rows.append([InlineKeyboardButton(text="📡 Получить сигнал", callback_data="menu:get")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    # удалить предыдущее окно бота
    last_id = getattr(u, "last_bot_message_id", None)
    if last_id:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=last_id)
        except Exception:
            pass

    # отправить картинку, если есть
    img_path = IMG_DIR / "menu.jpg"
    if img_path.exists():
        try:
            sent = await m.answer_photo(
                photo=FSInputFile(str(img_path)),
                caption=title,
                reply_markup=kb
            )
            await _set_last_bot_message_id(m.from_user.id, sent.message_id)
            return
        except Exception:
            pass

    # fallback: просто текст
    sent = await m.answer(title, reply_markup=kb, disable_web_page_preview=True)
    await _set_last_bot_message_id(m.from_user.id, sent.message_id)


# ===== команды/коллбеки =====
@router.message(Command("menu"))
async def cmd_menu(m: Message):
    u = await _get_user(m.from_user.id)
    lang = (u.lang if u and u.lang else "ru")
    await render_main_menu(m, lang, vip=bool(getattr(u, "has_vip", False)))


@router.callback_query(F.data == "go:menu")
async def cb_go_menu(call: CallbackQuery):
    u = await _get_user(call.from_user.id)
    lang = (u.lang if u and u.lang else "ru")
    await render_main_menu(call.message, lang, vip=bool(getattr(u, "has_vip", False)))
    await call.answer()
