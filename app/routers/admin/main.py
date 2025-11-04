from __future__ import annotations

from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from app.config import settings
from app.db.session import async_session
from app.models.user import User

# Подроутеры админки
from app.routers.admin import settings as settings_router
from app.routers.admin import stats as stats_router
from app.routers.admin import broadcast as broadcast_router
from app.routers.admin import postbacks as postbacks_router
from app.routers.admin import users as users_router  # <— НОВОЕ

router = Router(name=__name__)

# Подключаем дочерние роутеры админки
router.include_router(settings_router.router)
router.include_router(stats_router.router)
router.include_router(broadcast_router.router)
router.include_router(postbacks_router.router)
router.include_router(users_router.router)  # <— НОВОЕ


# === helpers ===
async def _get_user(tg_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.get(User, tg_id)


async def _set_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(id=tg_id)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        user.last_bot_message_id = message_id
        await session.commit()


async def _render_one_window(ctx, text: str, kb: InlineKeyboardMarkup):
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

    # удалить прошлое окно
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


# === keyboards ===
def _kb_admin_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users"),  # <— НОВОЕ
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки",  callback_data="admin:settings"),
            InlineKeyboardButton(text="📣 Рассылка",   callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="📮 Постбэки",   callback_data="admin:postbacks"),
        ],
    ])


def _kb_back_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back")],
    ])


# === /admin ===
@router.message(Command("admin"))
async def cmd_admin(m: Message):
    if not settings.is_admin(m.from_user.id):
        await m.answer("⛔ Доступ запрещён.")
        return

    text = (
        "<b>Админ-панель</b>\n\n"
        "Выберите раздел:\n"
        "• ⚙️ Настройки — пороги, ссылки, флаги шагов\n"
        "• 📣 Рассылка — отправка сообщений по сегментам\n"
        "• 📊 Статистика — воронка и суммы депозитов\n"
        "• 📮 Постбэки — последние события и синхронизация\n"
        "• 👥 Пользователи — список, поиск, карточки"
    )
    await _render_one_window(m, text, _kb_admin_root())


@router.callback_query(F.data == "admin:back")
async def cb_admin_back(call: CallbackQuery):
    if not settings.is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    text = (
        "<b>Админ-панель</b>\n\n"
        "Выберите раздел:\n"
        "• ⚙️ Настройки — пороги, ссылки, флаги шагов\n"
        "• 📣 Рассылка — отправка сообщений по сегментам\n"
        "• 📊 Статистика — воронка и суммы депозитов\n"
        "• 📮 Постбэки — последние события и синхронизация\n"
        "• 👥 Пользователи — список, поиск, карточки"
    )
    await _render_one_window(call, text, _kb_admin_root())
    await call.answer()
