# app/main.py
import asyncio
import logging
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.client.default import DefaultBotProperties

from app.config import settings
from app.db.session import async_session, engine
from app.models.base import Base
from app.models.user import User
from app.services.i18n import load_lang
from app.services.users import decide_next_step, mark_regular_once_shown, mark_vip_once_shown
from app.services.subscriptions import verify_and_cache
from app.services.postbacks import recompute_user_from_postbacks

# Routers
from app.routers import common, menu, checks, postbacks
from app.routers.admin import main as admin_main

# HTTP приёмник постбэков (aiohttp)
from app.web.postbacks import start_postback_server

# ==== Роутер именно этого файла (обработчики /start и языка) ====
router = Router(name=__name__)

# ==== I18N / IMAGES ====
I18N_DIR = Path(__file__).parent / "assets" / "i18n"
IMG_DIR = Path(__file__).parent / "assets" / "images"
SUPPORTED_LANGS = ("ru", "en", "es", "uk")

_text_cache = {code: load_lang(code, I18N_DIR) for code in SUPPORTED_LANGS}

DEFAULT_TEXTS = {
    "screen.language.title": {"ru": "Выберите язык", "en": "Choose language", "es": "Elige idioma", "uk": "Обери мову"},
    "screen.menu.title": {"ru": "Главное меню", "en": "Main menu", "es": "Menú principal", "uk": "Головне меню"},
    "screen.menu.desc": {
        "ru": "Нажмите «Получить сигнал», чтобы пройти проверку доступа.",
        "en": "Tap “Get signal” to pass access checks.",
        "es": "Pulsa “Obtener señal” para pasar las comprobaciones.",
        "uk": "Натисніть “Отримати сигнал”, щоб пройти перевірки доступу.",
    },
    "btn.get_signal": {"ru": "Получить сигнал", "en": "Get signal", "es": "Obtener señal", "uk": "Отримати сигнал"},
    "btn.vip_signals": {"ru": "VIP сигналы", "en": "VIP signals", "es": "Señales VIP", "uk": "VIP сигнали"},
    "btn.support": {"ru": "Поддержка", "en": "Support", "es": "Soporte", "uk": "Підтримка"},
    "btn.back_menu": {"ru": "⬅️ В меню", "en": "⬅️ Menu", "es": "⬅️ Menú", "uk": "⬅️ Меню"},
}

def t(lang: str, key: str) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "ru"
    bucket = _text_cache.get(lang) or {}
    return bucket.get(key) or DEFAULT_TEXTS.get(key, {}).get(lang, key)

# ==== DB helpers ====
async def ensure_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_or_create_user(tg_id: int, lang: Optional[str] = None, ref_code: Optional[str] = None) -> User:
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id)
            if lang:
                user.lang = lang
            if ref_code:
                user.ref_code = ref_code
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            updated = False
            if lang and user.lang != lang:
                user.lang = lang
                updated = True
            if ref_code and not user.ref_code:
                user.ref_code = ref_code
                updated = True
            if updated:
                await session.commit()
        return user

async def update_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            return
        user.last_bot_message_id = message_id
        await session.commit()

# ==== Keyboards ====
def kb_language() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ],
        [
            InlineKeyboardButton(text="🇪🇸 Español", callback_data="lang:es"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
        ],
    ])

# ==== One-window with image (для экрана выбора языка) ====
async def send_window_with_image(bot: Bot, m: Message, caption_html: str, reply_markup: InlineKeyboardMarkup, image_name: str):
    # удалить прошлое сообщение бота, если было
    last_id = None
    async with async_session() as session:
        user = await session.get(User, m.from_user.id)
        if user:
            last_id = user.last_bot_message_id
    if last_id:
        try:
            await bot.delete_message(chat_id=m.chat.id, message_id=last_id)
        except Exception:
            pass

    img_path = IMG_DIR / image_name
    if img_path.exists():
        try:
            sent = await m.answer_photo(photo=FSInputFile(str(img_path)), caption=caption_html, reply_markup=reply_markup)
            await update_last_bot_message_id(m.from_user.id, sent.message_id)
            return
        except Exception:
            pass

    # fallback — просто текст
    sent = await m.answer(caption_html, reply_markup=reply_markup)
    await update_last_bot_message_id(m.from_user.id, sent.message_id)

# ==== Handlers (/start и выбор языка) ====
@router.message(CommandStart())
async def cmd_start(message: Message):
    logging.info("CMD /start from %s", message.from_user.id)

    # deep link ref
    ref_code = None
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            ref_code = parts[1].strip() or None

    user = await get_or_create_user(message.from_user.id, ref_code=ref_code)

    # если язык уже выбран — сразу главное меню
    if user.lang:
        await menu.render_main_menu(message, user.lang, vip=user.has_vip)
        return

    # иначе — экран выбора языка
    await send_window_with_image(
        message.bot,
        message,
        caption_html=t("ru", "screen.language.title"),
        reply_markup=kb_language(),
        image_name="language.jpg",
    )

@router.callback_query(F.data == "go:lang")
async def on_go_lang(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    await update_last_bot_message_id(call.from_user.id, None)

    await send_window_with_image(
        call.message.bot,
        call.message,
        caption_html=t("ru", "screen.language.title"),
        reply_markup=kb_language(),
        image_name="language.jpg",
    )
    await call.answer()

@router.callback_query(F.data.startswith("lang:"))
async def on_language_pick(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    await get_or_create_user(call.from_user.id, lang=lang)

    try:
        await call.message.delete()
    except Exception:
        pass
    await update_last_bot_message_id(call.from_user.id, None)

    await menu.render_main_menu(call.message, lang, vip=None)
    await call.answer()

@router.callback_query(F.data == "menu:get")
async def menu_get(call: CallbackQuery):
    from app.routers import checks  # локальный импорт
    async with async_session() as session:
        user: User = await session.get(User, call.from_user.id)
        if not user:
            user = User(id=call.from_user.id)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        if settings.REQUIRE_SUBSCRIPTION:
            channel_id = settings.sub_channel_id()
            try:
                await verify_and_cache(call.message.bot, call.from_user.id, channel_id)
            except Exception:
                pass

        try:
            await recompute_user_from_postbacks(call.from_user.id)
        except Exception:
            pass

        await session.flush()
        user = await session.get(User, call.from_user.id)

        decision = decide_next_step(user)
        lang = user.lang if user.lang in SUPPORTED_LANGS else "ru"

        if decision.step == "subscription":
            await call.answer()
            await checks.show_subscription(call)
            return
        if decision.step == "registration":
            await call.answer()
            await checks.show_registration(call)
            return
        if decision.step == "deposit":
            await call.answer()
            await checks.show_deposit(call)
            return
        if decision.step == "vip_once":
            mark_vip_once_shown(user)
            await session.commit()
            await call.answer()
            await checks.show_vip_access(call)
            return
        if decision.step == "access_ok_once":
            mark_regular_once_shown(user)
            await session.commit()
            await call.answer()
            await checks.show_access_ok(call)
            return
        if decision.step in ("open_vip", "open_regular"):
            vip = (decision.step == "open_vip")
            await call.answer()
            text = f"<b>{t(lang, 'screen.menu.title')}</b>\n\n{t(lang, 'screen.menu.desc')}"
            try:
                await call.message.delete()
            except Exception:
                pass
            sent = await call.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text=(DEFAULT_TEXTS["btn.vip_signals"]["ru"] if vip else DEFAULT_TEXTS["btn.get_signal"]["ru"]),
                        url=(settings.MINIAPP_LINK_VIP if vip else settings.MINIAPP_LINK_REGULAR)
                    )],
                    [InlineKeyboardButton(text=t(lang, "btn.back_menu"), callback_data="go:menu")],
                ])
            )
            await update_last_bot_message_id(call.from_user.id, sent.message_id)
            return

    await call.answer("Попробуйте ещё раз.", show_alert=False)

# ==== Entry point ====
async def main():
    logging.basicConfig(level=logging.INFO)
    await ensure_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Лёгкий логгер входящих сообщений (функция-middleware)
    from aiogram import types

    @dp.update.outer_middleware()
    async def log_all(handler, event, data):
        if isinstance(event, types.Message):
            logging.info("MSG: %r", event.text)
        return await handler(event, data)

    # HTTP сервер постбэков
    asyncio.create_task(start_postback_server(bot))

    # ВАЖНО: наш локальный роутер с /start — ПЕРВЫМ
    dp.include_router(router)
    dp.include_router(common.router)
    dp.include_router(menu.router)
    dp.include_router(checks.router)
    dp.include_router(admin_main.router)
    dp.include_router(postbacks.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
