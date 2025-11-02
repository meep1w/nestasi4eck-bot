from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from app.db.session import async_session
from app.models.user import User
from app.services.i18n import load_lang

router = Router(name=__name__)

# ==== I18N ====
I18N_DIR = Path(__file__).resolve().parents[1] / "assets" / "i18n"
SUPPORTED_LANGS = ("ru", "en", "es", "uk")
_text_cache = {code: load_lang(code, I18N_DIR) for code in SUPPORTED_LANGS}

DEFAULT_TEXTS = {
    "screen.language.title": {
        "ru": "Выберите язык",
        "en": "Choose language",
        "es": "Elige idioma",
        "uk": "Обери мову",
    },
    "screen.menu.title": {
        "ru": "Главное меню",
        "en": "Main menu",
        "es": "Menú principal",
        "uk": "Головне меню",
    },
    "screen.menu.desc": {
        "ru": "Нажмите «Получить сигнал», чтобы пройти проверку доступа.",
        "en": "Tap “Get signal” to pass access checks.",
        "es": "Pulsa “Obtener señal” para pasar las comprobaciones.",
        "uk": "Натисніть “Отримати сигнал”, щоб пройти перевірки доступу.",
    },
    "btn.get_signal": {
        "ru": "Получить сигнал",
        "en": "Get signal",
        "es": "Obtener señal",
        "uk": "Отримати сигнал",
    },
    "btn.vip_signals": {
        "ru": "VIP сигналы",
        "en": "VIP signals",
        "es": "Señales VIP",
        "uk": "VIP сигнали",
    },
    "btn.support": {
        "ru": "Поддержка",
        "en": "Support",
        "es": "Soporte",
        "uk": "Підтримка",
    },
    "btn.back_menu": {
        "ru": "⬅️ В меню",
        "en": "⬅️ Menu",
        "es": "⬅️ Menú",
        "uk": "⬅️ Меню",
    },
    "help.text": {
        "ru": "Команды:\n/lang — смена языка\n/menu — открыть главное меню\n/help — помощь",
        "en": "Commands:\n/lang — change language\n/menu — open main menu\n/help — help",
        "es": "Comandos:\n/lang — cambiar idioma\n/menu — abrir menú principal\n/help — ayuda",
        "uk": "Команди:\n/lang — змінити мову\n/menu — відкрити головне меню\n/help — допомога",
    },
}


def t(lang: str, key: str) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "ru"
    bucket = _text_cache.get(lang) or {}
    if key in bucket and bucket[key]:
        return bucket[key]
    return DEFAULT_TEXTS.get(key, {}).get(lang, key)


# ==== БАЗОВЫЕ УТИЛИТЫ ====
async def get_or_create_user(tg_id: int, lang: Optional[str] = None) -> User:
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id)
            if lang:
                user.lang = lang
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            if lang and user.lang != lang:
                user.lang = lang
                await session.commit()
        return user


async def get_user_lang(tg_id: int) -> str:
    async with async_session() as session:
        user = await session.get(User, tg_id)
        return user.lang if user and user.lang in SUPPORTED_LANGS else "ru"


async def update_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            return
        user.last_bot_message_id = message_id
        await session.commit()


# ==== КЛАВИАТУРЫ ====
def kb_language() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="common:lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="common:lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇪🇸 Español", callback_data="common:lang:es"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="common:lang:uk"),
        ],
    ])


def kb_main(lang: str, vip: bool = False) -> InlineKeyboardMarkup:
    btn_label = t(lang, "btn.vip_signals") if vip else t(lang, "btn.get_signal")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_label, callback_data="menu:get")],
        [InlineKeyboardButton(text=t(lang, "btn.support"), url="https://t.me/")],
    ])


# ==== HELP / LANG / MENU ====
@router.message(Command("help"))
async def cmd_help(m: Message):
    lang = await get_user_lang(m.from_user.id)
    await m.answer(t(lang, "help.text"))


@router.message(Command("lang"))
async def cmd_lang(m: Message):
    # показать окно выбора языка (с удалением предыдущего бот-сообщения, если было)
    last_id = None
    async with async_session() as session:
        user = await session.get(User, m.from_user.id)
        if not user:
            user = await get_or_create_user(m.from_user.id)
        last_id = user.last_bot_message_id

    if last_id:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=last_id)
        except Exception:
            pass

    sent = await m.answer(t("ru", "screen.language.title"), reply_markup=kb_language())
    await update_last_bot_message_id(m.from_user.id, sent.message_id)


@router.callback_query(F.data.startswith("common:lang:"))
async def on_lang_pick(call: CallbackQuery):
    lang = call.data.split(":", 2)[2]
    await get_or_create_user(call.from_user.id, lang=lang)

    # удалим сообщение выбора языка
    try:
        await call.message.delete()
    except Exception:
        pass
    await update_last_bot_message_id(call.from_user.id, None)

    text = f"<b>{t(lang, 'screen.menu.title')}</b>\n\n{t(lang, 'screen.menu.desc')}"
    sent = await call.message.answer(text, reply_markup=kb_main(lang, vip=False))
    await update_last_bot_message_id(call.from_user.id, sent.message_id)
    await call.answer()


@router.message(Command("menu"))
async def cmd_menu(m: Message):
    lang = await get_user_lang(m.from_user.id)

    # Удалим предыдущее окно бота, если есть
    last_id = None
    async with async_session() as session:
        user = await session.get(User, m.from_user.id)
        if not user:
            user = await get_or_create_user(m.from_user.id, lang=lang)
        last_id = user.last_bot_message_id

    if last_id:
        try:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=last_id)
        except Exception:
            pass

    text = f"<b>{t(lang, 'screen.menu.title')}</b>\n\n{t(lang, 'screen.menu.desc')}"
    sent = await m.answer(text, reply_markup=kb_main(lang, vip=False))
    await update_last_bot_message_id(m.from_user.id, sent.message_id)
