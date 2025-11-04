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

I18N_DIR = Path(__file__).resolve().parents[1] / "assets" / "i18n"

# РОВНО 6 ЯЗЫКОВ
SUPPORTED_LANGS = ("en", "ru", "hi", "ar", "es", "fr")
_text_cache = {code: load_lang(code, I18N_DIR) for code in SUPPORTED_LANGS}

DEFAULT_TEXTS = {
    "screen.language.title": {
        "en": "Choose language",
        "ru": "Выберите язык",
        "hi": "भाषा चुनें",
        "ar": "اختر اللغة",
        "es": "Elige idioma",
        "fr": "Choisissez la langue",
        "ro": "Alege limba"
    },

    # Главное меню — только заголовок, без описания
    "screen.menu.title": {
        "en": "Main menu",
        "ru": "Главное меню",
        "hi": "मुख्य मेनू",
        "ar": "القائمة الرئيسية",
        "es": "Menú principal",
        "fr": "Menu principal",
        "ro": "Meniu principal"
    },
    "screen.menu.desc": {
        "en": "",
        "ru": "",
        "hi": "",
        "ar": "",
        "es": "",
        "fr": "",
        "ro": ""
    },

    # Кнопки
    "btn.get_signal": {
        "en": "📡 Get signal",
        "ru": "📡 Получить сигнал",
        "hi": "📡 सिग्नल प्राप्त करें",
        "ar": "📡 الحصول على الإشارة",
        "es": "📡 Obtener señal",
        "fr": "📡 Obtenir le signal",
        "ro": "📡 Obține semnal"
    },
    "btn.support": {
        "en": "🛟 Support",
        "ru": "🛟 Поддержка",
        "hi": "🛟 सहायता",
        "ar": "🛟 الدعم",
        "es": "🛟 Soporte",
        "fr": "🛟 Support",
        "ro": "🛟 Asistență"
    },

    # Help (локализовано; команды остаются как есть)
    "help.text": {
        "en": "Commands:\n/lang — change language 🌐\n/menu — open main menu 🏠\n/help — show help ❓",
        "ru": "Команды:\n/lang — сменить язык 🌐\n/menu — открыть главное меню 🏠\n/help — показать помощь ❓",
        "hi": "कमांड्स:\n/lang — भाषा बदलें 🌐\n/menu — मुख्य मेनू खोलें 🏠\n/help — सहायता दिखाएँ ❓",
        "ar": "الأوامر:\n/lang — تغيير اللغة 🌐\n/menu — فتح القائمة الرئيسية 🏠\n/help — عرض المساعدة ❓",
        "es": "Comandos:\n/lang — cambiar idioma 🌐\n/menu — abrir menú principal 🏠\n/help — mostrar ayuda ❓",
        "fr": "Commandes :\n/lang — changer la langue 🌐\n/menu — ouvrir le menu principal 🏠\n/help — afficher l’aide ❓",
        "ro": "Comenzi:\n/lang — schimbă limba 🌐\n/menu — deschide meniul principal 🏠\n/help — afișează ajutorul ❓"
    },
}



def t(lang: str, key: str) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "en"
    bucket = _text_cache.get(lang) or {}
    val = bucket.get(key)
    if not val:
        val = DEFAULT_TEXTS.get(key, {}).get(lang)
    if not val:
        val = DEFAULT_TEXTS.get(key, {}).get("en") or DEFAULT_TEXTS.get(key, {}).get("ru") or key
    return val

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
        return user.lang if user and user.lang in SUPPORTED_LANGS else "en"

async def update_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            return
        user.last_bot_message_id = message_id
        await session.commit()

# ==== КЛАВИАТУРЫ ====
def kb_language() -> InlineKeyboardMarkup:
    # 4 + 3 на две строки
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇷🇺 Русский",  callback_data="lang:ru"),
            InlineKeyboardButton(text="🇮🇳 हिन्दी",    callback_data="lang:hi"),
            InlineKeyboardButton(text="🇦🇪 العربية",  callback_data="lang:ar"),
        ],
        [
            InlineKeyboardButton(text="🇪🇸 Español",  callback_data="lang:es"),
            InlineKeyboardButton(text="🇫🇷 Français", callback_data="lang:fr"),
            InlineKeyboardButton(text="🇷🇴 Română",   callback_data="lang:ro"),
        ],
    ])

def kb_main(lang: str, vip: bool = False) -> InlineKeyboardMarkup:
    btn_label = t(lang, "btn.get_signal")
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

    sent = await m.answer(t("en", "screen.language.title"), reply_markup=kb_language())
    await update_last_bot_message_id(m.from_user.id, sent.message_id)

@router.callback_query(F.data.startswith("common:lang:"))
async def on_lang_pick(call: CallbackQuery):
    lang = call.data.split(":", 2)[2]
    await get_or_create_user(call.from_user.id, lang=lang)

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
