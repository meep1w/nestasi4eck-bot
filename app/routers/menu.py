# app/routers/menu.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from app.db.session import async_session
from app.models.user import User
from app.services.i18n import load_lang
from app.config import settings

router = Router(name="app.routers.menu")

# --- I18N / IMAGES ---
# Важно: ассеты лежат в app/assets/*, значит parents[1]
I18N_DIR = Path(__file__).resolve().parents[1] / "assets" / "i18n"
IMG_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"
SUPPORTED_LANGS = ("ru", "en", "es", "uk")

_text_cache = {code: load_lang(code, I18N_DIR) for code in SUPPORTED_LANGS}
DEFAULT_TEXTS = {
    "screen.menu.title": {"ru": "Главное меню", "en": "Main menu", "es": "Menú principal", "uk": "Головне меню"},
    "screen.menu.desc": {
        "ru": "Нажмите «Получить сигнал», чтобы пройти проверку доступа.",
        "en": "Tap “Get signal” to pass access checks.",
        "es": "Pulsa “Obtener señal” para pasar las comprobaciones.",
        "uk": "Натисніть “Отримати сигнал”, щоб пройти перевірки доступу.",
    },
    "btn.support": {"ru": "🛟 Поддержка", "en": "🛟 Support", "es": "🛟 Soporte", "uk": "🛟 Підтримка"},
    "btn.instruction": {"ru": "📘 Инструкция", "en": "📘 Guide", "es": "📘 Guía", "uk": "📘 Інструкція"},
    "btn.change_lang": {"ru": "🌐 Сменить язык", "en": "🌐 Change language", "es": "🌐 Cambiar idioma", "uk": "🌐 Змінити мову"},
    "btn.get_signal": {"ru": "📡 Получить сигнал", "en": "📡 Get signal", "es": "📡 Obtener señal", "uk": "📡 Отримати сигнал"},
    "btn.vip_signals": {"ru": "👑 VIP сигналы", "en": "👑 VIP signals", "es": "👑 Señales VIP", "uk": "👑 VIP сигнали"},
}

def t(lang: str, key: str) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "ru"
    bucket = _text_cache.get(lang) or {}
    return bucket.get(key) or DEFAULT_TEXTS.get(key, {}).get(lang, key)

# --- DB helpers ---
async def _update_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        user.last_bot_message_id = message_id
        await session.commit()

async def _get_last_bot_message_id(tg_id: int) -> Optional[int]:
    async with async_session() as session:
        user = await session.get(User, tg_id)
        return user.last_bot_message_id if user else None

# --- UI helpers ---
def _kb_main(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn.support"), url=settings.SUPPORT_URL),
            InlineKeyboardButton(text=t(lang, "btn.instruction"), callback_data="go:instruction"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn.change_lang"), callback_data="go:lang"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn.get_signal"), callback_data="menu:get"),
        ],
    ])

async def _send_window_with_image(ctx: Message | CallbackQuery, caption_html: str, kb: InlineKeyboardMarkup, image_name: str):
    # унифицируем контекст
    if isinstance(ctx, Message):
        chat_id = ctx.chat.id
        user_id = ctx.from_user.id
        bot = ctx.bot
        send_text = ctx.answer
        send_photo = ctx.answer_photo
    else:
        chat_id = ctx.message.chat.id
        user_id = ctx.from_user.id
        bot = ctx.message.bot
        send_text = ctx.message.answer
        send_photo = ctx.message.answer_photo

    # удалить предыдущее «окно» бота
    last_id = await _get_last_bot_message_id(user_id)
    if last_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=last_id)
        except Exception:
            pass

    # отправить картинку, если есть
    img_path = IMG_DIR / image_name
    if img_path.exists():
        try:
            sent = await send_photo(photo=FSInputFile(str(img_path)), caption=caption_html, reply_markup=kb)
            await _update_last_bot_message_id(user_id, sent.message_id)
            return
        except Exception:
            # если вдруг Telegram не принял фото — фолбэк на текст
            pass

    # фолбэк — просто текст
    sent = await send_text(caption_html, reply_markup=kb, disable_web_page_preview=True)
    await _update_last_bot_message_id(user_id, sent.message_id)

# --- public API ---
async def render_main_menu(ctx: Message | CallbackQuery, lang: str, vip: Optional[bool]):
    """
    Отрисовать главное меню. Параметр vip здесь не меняет кнопки —
    доступ к мини-аппам решается дальше в логике checks/menu:get.
    """
    title = f"<b>{t(lang, 'screen.menu.title')}</b>"
    desc = t(lang, "screen.menu.desc")
    await _send_window_with_image(
        ctx,
        caption_html=f"{title}\n\n{desc}",
        kb=_kb_main(lang),
        image_name="menu.jpg",
    )

# --- handlers ---
@router.callback_query(F.data == "go:menu")
async def cb_go_menu(call: CallbackQuery):
    # определим язык пользователя и перерисуем меню
    async with async_session() as session:
        user = await session.get(User, call.from_user.id)
        lang = user.lang if (user and user.lang in SUPPORTED_LANGS) else "ru"
    await render_main_menu(call, lang, vip=None)
    await call.answer()
