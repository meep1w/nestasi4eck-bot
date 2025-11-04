from __future__ import annotations

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.exceptions import TelegramBadRequest

from app.config import settings

router = Router(name=__name__)

# Простое ожидание ввода (in-memory)
_pending: dict[int, str] = {}


def _onoff(v: bool) -> str:
    return "ON" if v else "OFF"


def _view_settings() -> str:
    ch = settings.SUB_CHANNEL_ID
    ch_view = f"<code>{ch}</code>" if ch is not None else "—"

    return (
        "🛠 <b>Настройки доступа</b>\n\n"
        f"• Требовать подписку: <b>{_onoff(settings.REQUIRE_SUBSCRIPTION)}</b>\n"
        f"• Требовать депозит: <b>{_onoff(settings.REQUIRE_DEPOSIT)}</b>\n"
        f"• Канал (ID): {ch_view}\n\n"
        f"• Порог доступа (ACCESS): <b>{int(settings.ACCESS_THRESHOLD_USD)}$</b>\n"
        f"• Порог VIP: <b>{int(settings.VIP_THRESHOLD_USD)}$</b>\n\n"
        "🔗 <b>Ссылки</b>\n"
        f"• Реф. ссылка: <code>{settings.REF_LINK}</code>\n"
        f"• Поддержка: <code>{settings.SUPPORT_URL}</code>\n"
        f"• Ссылка на канал: <code>{settings.SUB_CHANNELS_URL}</code>\n"
    )


def _kb() -> InlineKeyboardMarkup:
    """
    Без мини-аппов. Две кнопки в строке.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🪪 Подписка: {_onoff(settings.REQUIRE_SUBSCRIPTION)}", callback_data="admin:toggle:sub"),
            InlineKeyboardButton(text=f"💳 Депозит: {_onoff(settings.REQUIRE_DEPOSIT)}",       callback_data="admin:toggle:dep"),
        ],
        [
            InlineKeyboardButton(text="🆔 Канал ID",   callback_data="admin:set:channel"),
            InlineKeyboardButton(text="🔗 Канал URL",   callback_data="admin:set:suburl"),
        ],
        [
            InlineKeyboardButton(text="💵 Мин. деп",    callback_data="admin:set:access"),
            InlineKeyboardButton(text="👑 Порог ВИП",   callback_data="admin:set:vip"),
        ],
        [
            InlineKeyboardButton(text="🔁 Рев ссылка",  callback_data="admin:set:ref"),
            InlineKeyboardButton(text="🆘 Ссылка поддержки", callback_data="admin:set:support"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад",         callback_data="admin:back")],
    ])


# === OPEN ===
@router.callback_query(F.data == "admin:settings")
async def open_settings(call: CallbackQuery):
    try:
        await call.message.edit_text(_view_settings(), reply_markup=_kb(), disable_web_page_preview=True)
    except TelegramBadRequest:
        await call.message.answer(_view_settings(), reply_markup=_kb(), disable_web_page_preview=True)
    await call.answer()


# === TOGGLES ===
@router.callback_query(F.data == "admin:toggle:sub")
async def toggle_sub(call: CallbackQuery):
    setattr(settings, "REQUIRE_SUBSCRIPTION", not settings.REQUIRE_SUBSCRIPTION)
    await call.message.edit_text(_view_settings(), reply_markup=_kb(), disable_web_page_preview=True)
    await call.answer("Готово")

@router.callback_query(F.data == "admin:toggle:dep")
async def toggle_dep(call: CallbackQuery):
    setattr(settings, "REQUIRE_DEPOSIT", not settings.REQUIRE_DEPOSIT)
    await call.message.edit_text(_view_settings(), reply_markup=_kb(), disable_web_page_preview=True)
    await call.answer("Готово")


# === HELPERS FOR INPUT ===
async def _ask(call: CallbackQuery, key: str, prompt: str):
    _pending[call.from_user.id] = key
    await call.message.answer(f"✍️ {prompt}\n\nОтправьте одним сообщением.", reply_markup=ReplyKeyboardRemove())
    await call.answer()


# === SETTERS (ask) ===
@router.callback_query(F.data == "admin:set:channel")
async def ask_channel(call: CallbackQuery):
    await _ask(call, "SUB_CHANNEL_ID", "Введите ID канала (целое число, со знаком «-» для каналов).")

@router.callback_query(F.data == "admin:set:access")
async def ask_access(call: CallbackQuery):
    await _ask(call, "ACCESS_THRESHOLD_USD", "Введите новый порог доступа, $ (например 100).")

@router.callback_query(F.data == "admin:set:vip")
async def ask_vip(call: CallbackQuery):
    await _ask(call, "VIP_THRESHOLD_USD", "Введите новый порог VIP, $ (например 300).")

@router.callback_query(F.data == "admin:set:ref")
async def ask_ref(call: CallbackQuery):
    await _ask(call, "REF_LINK", "Вставьте новую реферальную ссылку.")

@router.callback_query(F.data == "admin:set:support")
async def ask_support(call: CallbackQuery):
    await _ask(call, "SUPPORT_URL", "Ссылка на поддержку.")

@router.callback_query(F.data == "admin:set:suburl")
async def ask_suburl(call: CallbackQuery):
    await _ask(call, "SUB_CHANNELS_URL", "Ссылка на канал подписки / хаб.")


# === TEXT INPUT SAVE ===
@router.message(F.text)
async def save_value(message: Message):
    key = _pending.pop(message.from_user.id, None)
    if not key:
        return

    raw = (message.text or "").strip()
    try:
        if key in {"ACCESS_THRESHOLD_USD", "VIP_THRESHOLD_USD"}:
            setattr(settings, key, float(raw.replace(",", ".")))
        elif key == "SUB_CHANNEL_ID":
            setattr(settings, key, int(raw))
        else:
            setattr(settings, key, raw)
        await message.answer("✅ Сохранено.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        return

    try:
        await message.answer(_view_settings(), reply_markup=_kb(), disable_web_page_preview=True)
    except TelegramBadRequest:
        pass
