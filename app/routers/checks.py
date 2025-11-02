from pathlib import Path
from typing import Optional, Iterable

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    FSInputFile,
)

from app.config import settings
from app.db.session import async_session
from app.models.user import User
from app.services.i18n import load_lang
from app.services.tracking import ensure_click_id, build_ref_link_with_click
from . import menu as menu_router  # для render_main_menu
from app.services.subscriptions import verify_and_cache

router = Router(name=__name__)

# === I18N ===
I18N_DIR = Path(__file__).resolve().parents[1] / "assets" / "i18n"
IMG_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"
SUPPORTED_LANGS = ("ru", "en", "es", "uk")
_text_cache = {code: load_lang(code, I18N_DIR) for code in SUPPORTED_LANGS}

DEFAULT_TEXTS = {
    # Заголовки
    "screen.registration.title": {"ru": "Проверка регистрации","en": "Registration check","es": "Verificación de registro","uk": "Перевірка реєстрації"},
    "screen.subscription.title": {"ru": "Проверка подписки","en": "Subscription check","es": "Verificación de suscripción","uk": "Перевірка підписки"},
    "screen.deposit.title": {"ru": "Проверка депозита","en": "Deposit check","es": "Verificación del depósito","uk": "Перевірка депозиту"},
    "screen.access_ok.title": {"ru": "Доступ открыт","en": "Access granted","es": "Acceso concedido","uk": "Доступ відкрито"},
    "screen.vip.title": {"ru": "VIP доступ","en": "VIP access","es": "Acceso VIP","uk": "VIP доступ"},
    "screen.instruction.title": {"ru": "Инструкция","en": "Guide","es": "Guía","uk": "Інструкція"},
    # Описания
    "screen.registration.desc": {
        "ru": "Зарегистрируйтесь по ссылке. Проверка проходит автоматически, как только придёт постбэк.",
        "en": "Register via the link. We verify automatically once a postback arrives.",
        "es": "Regístrate con el enlace. La verificación es automática cuando llegue el postback.",
        "uk": "Зареєструйтесь за посиланням. Перевірка автоматична, щойно прийде постбек.",
    },
    "screen.subscription.desc": {
        "ru": "Подпишитесь на нужные каналы. Проверка выполняется автоматически при нажатии «📡 Получить сигнал».",
        "en": "Subscribe to the required channels. We verify automatically when you tap “📡 Get signal”.",
        "es": "Suscríbete a los canales requeridos. Verificamos automáticamente al pulsar “📡 Obtener señal”.",
        "uk": "Підпишіться на потрібні канали. Перевірка виконується автоматично при натисканні “📡 Отримати сигнал”.",
    },
    "screen.deposit.desc": {
        "ru": "Внесите депозит на сумму не менее {need}$ (суммарно). Текущий: {have}$. Проверка проходит автоматически по постбэкам.",
        "en": "Top up at least {need}$ in total. Current: {have}$. Verification is automatic via postbacks.",
        "es": "Recarga al menos {need}$ en total. Actual: {have}$. La verificación es automática por postbacks.",
        "uk": "Поповніть щонайменше на {need}$ сумарно. Поточний: {have}$. Перевірка автоматична через постбеки.",
    },
    "screen.access_ok.desc": {
        "ru": "Теперь вы можете открыть мини-апп и получить сигналы.",
        "en": "You can now open the mini-app and get signals.",
        "es": "Ahora puedes abrir la mini-app y recibir señales.",
        "uk": "Тепер ви можете відкрити міні-ап і отримувати сигнали.",
    },
    "screen.vip.desc": {
        "ru": "Открыт доступ к VIP сигналам. Удачной торговли!",
        "en": "VIP signals are unlocked. Trade well!",
        "es": "Se han desbloqueado señales VIP. ¡Éxitos!",
        "uk": "Відкрито доступ до VIP сигналів. Успіхів!",
    },
    "screen.instruction.desc": {
        "ru": (
            "1) 🌐 Выберите язык в /start\n"
            "2) 📨 Подпишитесь на канал(ы)\n"
            "3) 📝 Зарегистрируйтесь по реф-ссылке\n"
            "4) 💳 Внесите депозит ≥ порога для доступа (и ≥ VIP — для VIP)\n"
            "5) 📡 Нажмите «Получить сигнал» — бот сам всё проверит и откроет мини-апп\n\n"
            "Проверки идут автоматически по постбэкам и подписке. Если что-то не открылось — просто попробуйте снова."
        ),
        "en": (
            "1) 🌐 Pick language via /start\n"
            "2) 📨 Subscribe to channel(s)\n"
            "3) 📝 Register via referral link\n"
            "4) 💳 Deposit ≥ access threshold (and ≥ VIP for VIP)\n"
            "5) 📡 Tap “Get signal” — the bot verifies and opens the mini-app\n\n"
            "Checks are automatic via postbacks/subscription. If something’s not open yet — try again."
        ),
        "es": (
            "1) 🌐 Elige idioma con /start\n"
            "2) 📨 Suscríbete a los canales\n"
            "3) 📝 Regístrate con el enlace\n"
            "4) 💳 Depósito ≥ umbral de acceso (y ≥ VIP para VIP)\n"
            "5) 📡 Pulsa “Obtener señal” — el bot verifica y abre la mini-app\n\n"
            "Las comprobaciones son automáticas. Si algo no se abre aún — inténtalo de nuevo."
        ),
        "uk": (
            "1) 🌐 Оберіть мову через /start\n"
            "2) 📨 Підпишіться на канал(и)\n"
            "3) 📝 Зареєструйтесь за реф-посиланням\n"
            "4) 💳 Депозит ≥ порога доступу (і ≥ VIP — для VIP)\n"
            "5) 📡 Натисніть «Отримати сигнал» — бот сам перевірить і відкриє міні-ап\n\n"
            "Перевірки автоматичні. Якщо щось не відкривається — спробуйте ще раз."
        ),
    },
    # Кнопки
    "btn.register": {"ru": "📝 Зарегистрироваться","en": "📝 Register","es": "📝 Registrarme","uk": "📝 Зареєструватися"},
    "btn.subscribe": {"ru": "📨 Подписаться","en": "📨 Subscribe","es": "📨 Suscribirme","uk": "📨 Підписатися"},
    "btn.deposit": {"ru": "💳 Внести депозит","en": "💳 Top up","es": "💳 Recargar","uk": "💳 Поповнити"},
    "btn.support": {"ru": "🛟 Поддержка","en": "🛟 Support","es": "🛟 Soporte","uk": "🛟 Підтримка"},
    "btn.get_signal": {"ru": "📡 Получить сигнал","en": "📡 Get signal","es": "📡 Obtener señal","uk": "📡 Отримати сигнал"},
    "btn.vip_signals": {"ru": "👑 VIP сигналы","en": "👑 VIP signals","es": "👑 Señales VIP","uk": "👑 VIP сигнали"},
    "btn.back_menu": {"ru": "⬅️ Вернуться в главное меню","en": "⬅️ Back to Menu","es": "⬅️ Volver al menú","uk": "⬅️ Повернутися в меню"},
}

def t(lang: str, key: str, **fmt) -> str:
    lang = lang if lang in SUPPORTED_LANGS else "ru"
    bucket = _text_cache.get(lang) or {}
    raw = bucket.get(key) or DEFAULT_TEXTS.get(key, {}).get(lang, key)
    try:
        return raw.format(**fmt)
    except Exception:
        return raw


# === DB helpers ===
async def get_user(tg_id: int) -> Optional[User]:
    async with async_session() as session:
        return await session.get(User, tg_id)


async def set_last_bot_message_id(tg_id: int, message_id: Optional[int]):
    async with async_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            return
        user.last_bot_message_id = message_id
        await session.commit()


# === One-window (image + caption + buttons) ===
async def _send_window_with_image(message_or_call, caption_html: str, kb: InlineKeyboardMarkup, image_name: str):
    if isinstance(message_or_call, Message):
        chat_id = message_or_call.chat.id
        user_id = message_or_call.from_user.id
        bot = message_or_call.bot
        send_text = message_or_call.answer
        send_photo = message_or_call.answer_photo
    else:
        chat_id = message_or_call.message.chat.id
        user_id = message_or_call.from_user.id
        bot = message_or_call.message.bot
        send_text = message_or_call.message.answer
        send_photo = message_or_call.message.answer_photo

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

    img_path = IMG_DIR / image_name
    if img_path.exists():
        try:
            sent = await send_photo(photo=FSInputFile(str(img_path)), caption=caption_html, reply_markup=kb)
            await set_last_bot_message_id(user_id, sent.message_id)
            return
        except Exception:
            pass

    sent = await send_text(caption_html, reply_markup=kb)
    await set_last_bot_message_id(user_id, sent.message_id)


# === Keyboards ===
def kb_registration(lang: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.register"), url=url)],
        [InlineKeyboardButton(text=t(lang, "btn.back_menu"), callback_data="go:menu")],
    ])

def kb_subscription(lang: str, channels: Iterable[str] | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.subscribe"), url=settings.SUB_CHANNELS_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check:sub")],
        [InlineKeyboardButton(text=t(lang, "btn.back_menu"), callback_data="go:menu")],
    ])


def kb_deposit(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.deposit"), url=settings.REF_LINK)],
        [InlineKeyboardButton(text=t(lang, "btn.back_menu"), callback_data="go:menu")],
    ])

def kb_access_ok(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.support"), url=settings.SUPPORT_URL)],
        [InlineKeyboardButton(text=t(lang, "btn.get_signal"), callback_data="menu:get")],
    ])

def kb_vip(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.support"), url=settings.SUPPORT_URL)],
        [InlineKeyboardButton(text=t(lang, "btn.vip_signals"), callback_data="menu:get")],
    ])

def kb_instruction(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn.back_menu"), callback_data="go:menu")],
    ])


# === Screens ===
async def show_registration(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"

    # ensure click_id и сборка реф-ссылки с click_id
    click_id = await ensure_click_id(ctx.from_user.id)
    url = build_ref_link_with_click(click_id)

    text = f"<b>{t(lang, 'screen.registration.title')}</b>\n\n{t(lang, 'screen.registration.desc')}"
    await _send_window_with_image(ctx, text, kb_registration(lang, url), image_name="registration.jpg")

async def show_subscription(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"
    text = f"<b>{t(lang, 'screen.subscription.title')}</b>\n\n{t(lang, 'screen.subscription.desc')}"
    await _send_window_with_image(ctx, text, kb_subscription(lang), image_name="subscription.jpg")

async def show_deposit(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"
    need = settings.ACCESS_THRESHOLD_USD
    have = (user.deposit_total_usd if user else 0.0) or 0.0
    text = f"<b>{t(lang, 'screen.deposit.title')}</b>\n\n{t(lang, 'screen.deposit.desc', need=int(need), have=int(have))}"
    await _send_window_with_image(ctx, text, kb_deposit(lang), image_name="deposit.jpg")

async def show_access_ok(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"
    text = f"<b>{t(lang, 'screen.access_ok.title')}</b>\n\n{t(lang, 'screen.access_ok.desc')}"
    await _send_window_with_image(ctx, text, kb_access_ok(lang), image_name="access_ok.jpg")

async def show_vip_access(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"
    text = f"<b>{t(lang, 'screen.vip.title')}</b>\n\n{t(lang, 'screen.vip.desc')}"
    await _send_window_with_image(ctx, text, kb_vip(lang), image_name="vip.jpg")

async def show_instruction(ctx):
    user = await get_user(ctx.from_user.id)
    lang = user.lang if user else "ru"
    text = f"<b>{t(lang, 'screen.instruction.title')}</b>\n\n{t(lang, 'screen.instruction.desc')}"
    await _send_window_with_image(ctx, text, kb_instruction(lang), image_name="instruction.jpg")

# === DIRECT PUSH API (для web/postbacks) ===
from app.services.users import decide_next_step, mark_regular_once_shown, mark_vip_once_shown

async def _send_window_direct(bot, tg_id: int, caption_html: str, kb: InlineKeyboardMarkup, image_name: str):
    # удалить предыдущий экран
    last_id = None
    async with async_session() as session:
        u = await session.get(User, tg_id)
        lang = (u.lang if u else "ru") or "ru"
        if u:
            last_id = u.last_bot_message_id

    if last_id:
        try:
            await bot.delete_message(chat_id=tg_id, message_id=last_id)
        except Exception:
            pass

    img_path = IMG_DIR / image_name
    sent = None
    if img_path.exists():
        try:
            sent = await bot.send_photo(chat_id=tg_id, photo=FSInputFile(str(img_path)), caption=caption_html, reply_markup=kb)
        except Exception:
            sent = None
    if sent is None:
        sent = await bot.send_message(chat_id=tg_id, text=caption_html, reply_markup=kb)

    async with async_session() as session:
        u = await session.get(User, tg_id)
        if u:
            u.last_bot_message_id = sent.message_id
            await session.commit()

async def push_next_screen(bot, tg_id: int):
    """
    Определяет следующий шаг и высылает соответствующее окно пользователю.
    Показывает окна «Доступ открыт»/«VIP доступ» только один раз.
    """
    async with async_session() as session:
        u = await session.get(User, tg_id)
        if not u:
            return
        lang = u.lang or "ru"
        decision = decide_next_step(u)

    if decision.step == "subscription":
        text = f"<b>{t(lang, 'screen.subscription.title')}</b>\n\n{t(lang, 'screen.subscription.desc')}"
        await _send_window_direct(bot, tg_id, text, kb_subscription(lang), "subscription.jpg")
        return

    if decision.step == "registration":
        # Соберём ссылку с click_id
        click_id = await ensure_click_id(tg_id)
        url = build_ref_link_with_click(click_id)
        text = f"<b>{t(lang, 'screen.registration.title')}</b>\n\n{t(lang, 'screen.registration.desc')}"
        await _send_window_direct(bot, tg_id, text, kb_registration(lang, url), "registration.jpg")
        return

    if decision.step == "deposit":
        async with async_session() as session:
            u2 = await session.get(User, tg_id)
            need = settings.ACCESS_THRESHOLD_USD
            have = (u2.deposit_total_usd if u2 else 0.0) or 0.0
        text = f"<b>{t(lang, 'screen.deposit.title')}</b>\n\n{t(lang, 'screen.deposit.desc', need=int(need), have=int(have))}"
        await _send_window_direct(bot, tg_id, text, kb_deposit(lang), "deposit.jpg")
        return

    if decision.step == "vip_once":
        async with async_session() as session:
            u3 = await session.get(User, tg_id)
            mark_vip_once_shown(u3)
            await session.commit()
        text = f"<b>{t(lang, 'screen.vip.title')}</b>\n\n{t(lang, 'screen.vip.desc')}"
        await _send_window_direct(bot, tg_id, text, kb_vip(lang), "vip.jpg")
        return

    if decision.step == "access_ok_once":
        async with async_session() as session:
            u4 = await session.get(User, tg_id)
            mark_regular_once_shown(u4)
            await session.commit()
        text = f"<b>{t(lang, 'screen.access_ok.title')}</b>\n\n{t(lang, 'screen.access_ok.desc')}"
        await _send_window_direct(bot, tg_id, text, kb_access_ok(lang), "access_ok.jpg")
        return

    # open_vip / open_regular — дальше работаем через меню
    await menu_router.render_main_menu(
        type("msg", (), {"from_user": type("u", (), {"id": tg_id})(),
                         "chat": type("c", (), {"id": tg_id})(),
                         "bot": bot,
                         "answer": bot.send_message})(),
        lang,
        vip=(decision.step == "open_vip")
    )

# === Callbacks ===
@router.callback_query(F.data == "go:menu")
async def cb_go_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.lang if user else "ru"
    await menu_router.render_main_menu(call.message, lang, vip=bool(user.has_vip if user else False))

@router.callback_query(F.data == "go:instruction")
async def cb_go_instruction(call: CallbackQuery):
    await show_instruction(call)


@router.callback_query(F.data == "check:sub")
async def cb_check_subscription(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    lang = user.lang if user else "ru"

    # Проверяем подписку на все каналы из ENV
    try:
        chan_ids = settings.sub_channel_ids_list()
        await verify_and_cache(call.message.bot, call.from_user.id, chan_ids, require_all=settings.SUB_REQUIRE_ALL)
    except Exception:
        pass

    # После проверки — вычисляем следующий шаг и пушим экран
    from .checks import push_next_screen
    await push_next_screen(call.message.bot, call.from_user.id)
    await call.answer("Проверяю…")
