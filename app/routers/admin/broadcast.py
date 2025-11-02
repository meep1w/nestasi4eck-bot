from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from sqlalchemy import select, and_, or_, func

from app.config import settings
from app.db.session import async_session
from app.models.user import User

router = Router(name=__name__)

SUPPORTED_LANGS = ("ru", "en", "es", "uk")


# ========= Модель сегмента =========

@dataclass
class Segment:
    langs: set[str] = field(default_factory=set)          # пусто = все языки
    registered: Optional[bool] = None                    # None=все
    access_ok: Optional[bool] = None                     # None=все; True — >=ACCESS (или депозит выключен)
    vip: Optional[bool] = None                           # None=все
    subscribed: Optional[bool] = None                    # None=все

    def pretty(self) -> str:
        def s3(v, yes="да", no="нет"):
            return "любой" if v is None else (yes if v else no)
        parts: List[str] = []
        parts.append(f"языки: {','.join(sorted(self.langs)) if self.langs else 'все'}")
        parts.append(f"регистрация: {s3(self.registered)}")
        parts.append(f"доступ: {s3(self.access_ok)}")
        parts.append(f"VIP: {s3(self.vip)}")
        parts.append(f"подписка: {s3(self.subscribed)}")
        return "; ".join(parts)


# ========= Состояния =========

class BC(StatesGroup):
    picking_segment = State()
    waiting_text = State()
    waiting_media = State()
    waiting_button = State()
    confirming = State()
    broadcasting = State()


# ========= Общее: один экран без спама =========

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

    # удалить прошлый экран
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


# ========= Клавиатуры =========

def _chip(active: bool, label: str, cb: str) -> InlineKeyboardButton:
    # активный язык помечаем точкой
    dot = "• " if active else ""
    return InlineKeyboardButton(text=f"{dot}{label}", callback_data=cb)

def _tri(val: Optional[bool]) -> str:
    # для кнопок фильтров: — / ✅ / ❌
    return "—" if val is None else ("✅" if val else "❌")

def kb_segment(seg: Segment) -> InlineKeyboardMarkup:
    """
    Компактный сегмент:
    [RU][EN]
    [ES][UK]
    [📝 Рег: ?][🔓 Доступ: ?]
    [👑 VIP: ?][📫 Подписка: ?]
    [➡️ Дальше → Текст]
    [⬅️ Назад]
    """
    rows: List[List[InlineKeyboardButton]] = []

    # языки 2×2
    rows.append([_chip("ru" in seg.langs, "RU", "bc:lang:ru"),
                 _chip("en" in seg.langs, "EN", "bc:lang:en")])
    rows.append([_chip("es" in seg.langs, "ES", "bc:lang:es"),
                 _chip("uk" in seg.langs, "UK", "bc:lang:uk")])

    # бинарные фильтры — циклические
    rows.append([
        InlineKeyboardButton(text=f"📝 Рег: {_tri(seg.registered)}", callback_data="bc:cycle:registered"),
        InlineKeyboardButton(text=f"🔓 Доступ: {_tri(seg.access_ok)}", callback_data="bc:cycle:access"),
    ])
    rows.append([
        InlineKeyboardButton(text=f"👑 VIP: {_tri(seg.vip)}", callback_data="bc:cycle:vip"),
        InlineKeyboardButton(text=f"📫 Подписка: {_tri(seg.subscribed)}", callback_data="bc:cycle:subs"),
    ])

    rows.append([InlineKeyboardButton(text="➡️ Дальше → Текст", callback_data="bc:next:text")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_text_stage() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Добавить картинку (опционально)", callback_data="bc:add:media")],
        [InlineKeyboardButton(text="➡️ Дальше → Кнопка", callback_data="bc:next:button")],
        [InlineKeyboardButton(text="⬅️ Назад к сегменту", callback_data="bc:back:segment")],
    ])


def kb_media_stage() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить картинку", callback_data="bc:skip:media")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="bc:back:text")],
    ])


def kb_button_stage() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить кнопку", callback_data="bc:skip:button")],
        [InlineKeyboardButton(text="⬅️ Назад к тексту", callback_data="bc:back:text")],
        [InlineKeyboardButton(text="➡️ Дальше → Предпросмотр", callback_data="bc:next:preview")],
    ])


def kb_preview() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bc:send")],
        [InlineKeyboardButton(text="✏️ Текст", callback_data="bc:edit:text")],
        [InlineKeyboardButton(text="🖼 Картинка", callback_data="bc:add:media")],
        [InlineKeyboardButton(text="🔘 Кнопка", callback_data="bc:add:button")],
        [InlineKeyboardButton(text="⬅️ Назад к сегменту", callback_data="bc:back:segment")],
    ])


def _kb_user_button(text: Optional[str], url: Optional[str]) -> Optional[InlineKeyboardMarkup]:
    if not (text and url):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])


# ========= Утилиты сегмента =========

def _fmt_segment(seg: Segment) -> str:
    def label(v):
        return "любой" if v is None else ("✅ да" if v else "❌ нет")
    langs = (",".join(sorted(seg.langs)) if seg.langs else "все")
    return (
        "<b>📣 Новая рассылка</b>\n\n"
        f"🌍 Языки: <b>{langs}</b>\n"
        f"📝 Регистрация: <b>{label(seg.registered)}</b>\n"
        f"🔓 Доступ: <b>{label(seg.access_ok)}</b>\n"
        f"👑 VIP: <b>{label(seg.vip)}</b>\n"
        f"📫 Подписка: <b>{label(seg.subscribed)}</b>\n\n"
        "Выбери фильтры и нажми «Дальше → Текст»."
    )


async def _count_audience(seg: Segment) -> int:
    async with async_session() as session:
        q = select(func.count()).select_from(User)
        exprs = []

        if seg.langs:
            exprs.append(User.lang.in_(list(seg.langs)))

        if seg.registered is True:
            exprs.append(User.is_registered.is_(True))
        elif seg.registered is False:
            exprs.append(or_(User.is_registered.is_(False), User.is_registered.is_(None)))

        if seg.access_ok is True:
            if settings.REQUIRE_DEPOSIT:
                exprs.append(User.deposit_total_usd >= settings.ACCESS_THRESHOLD_USD)
        elif seg.access_ok is False:
            if settings.REQUIRE_DEPOSIT:
                exprs.append(or_(User.deposit_total_usd < settings.ACCESS_THRESHOLD_USD,
                                 User.deposit_total_usd.is_(None)))
            else:
                exprs.append(func.false())

        if seg.vip is True:
            exprs.append(or_(User.deposit_total_usd >= settings.VIP_THRESHOLD_USD, User.has_vip.is_(True)))
        elif seg.vip is False:
            exprs.append(and_(
                or_(User.deposit_total_usd < settings.VIP_THRESHOLD_USD, User.deposit_total_usd.is_(None)),
                or_(User.has_vip.is_(False), User.has_vip.is_(None)),
            ))

        if seg.subscribed is True:
            exprs.append(User.is_subscribed.is_(True))
        elif seg.subscribed is False:
            exprs.append(or_(User.is_subscribed.is_(False), User.is_subscribed.is_(None)))

        if exprs:
            q = q.where(and_(*exprs))

        return (await session.execute(q)).scalar_one()


async def _list_audience(seg: Segment) -> List[int]:
    async with async_session() as session:
        q = select(User.id)
        exprs = []

        if seg.langs:
            exprs.append(User.lang.in_(list(seg.langs)))

        if seg.registered is True:
            exprs.append(User.is_registered.is_(True))
        elif seg.registered is False:
            exprs.append(or_(User.is_registered.is_(False), User.is_registered.is_(None)))

        if seg.access_ok is True:
            if settings.REQUIRE_DEPOSIT:
                exprs.append(User.deposit_total_usd >= settings.ACCESS_THRESHOLD_USD)
        elif seg.access_ok is False:
            if settings.REQUIRE_DEPOSIT:
                exprs.append(or_(User.deposit_total_usd < settings.ACCESS_THRESHOLD_USD,
                                 User.deposit_total_usd.is_(None)))
            else:
                exprs.append(func.false())

        if seg.vip is True:
            exprs.append(or_(User.deposit_total_usd >= settings.VIP_THRESHOLD_USD, User.has_vip.is_(True)))
        elif seg.vip is False:
            exprs.append(and_(
                or_(User.deposit_total_usd < settings.VIP_THRESHOLD_USD, User.deposit_total_usd.is_(None)),
                or_(User.has_vip.is_(False), User.has_vip.is_(None)),
            ))

        if seg.subscribed is True:
            exprs.append(User.is_subscribed.is_(True))
        elif seg.subscribed is False:
            exprs.append(or_(User.is_subscribed.is_(False), User.is_subscribed.is_(None)))

        if exprs:
            q = q.where(and_(*exprs))

        ids = [x[0] for x in (await session.execute(q)).all()]
        return ids


# ========= Вход и выбор сегмента =========

@router.callback_query(F.data == "admin:broadcast")
async def enter_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    seg = Segment()
    await state.update_data(seg=seg, text=None, media=None, btn_text=None, btn_url=None)
    await state.set_state(BC.picking_segment)
    await call.answer()
    await _render_one(call, _fmt_segment(seg), kb_segment(seg))


@router.callback_query(F.data.startswith("bc:lang:"))
async def toggle_lang(call: CallbackQuery, state: FSMContext):
    code = call.data.split(":", 2)[2]
    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()
    if code in seg.langs:
        seg.langs.remove(code)
    else:
        seg.langs.add(code)
    await state.update_data(seg=seg)
    await call.answer()
    await _render_one(call, _fmt_segment(seg), kb_segment(seg))


@router.callback_query(F.data.startswith("bc:cycle:"))
async def cycle_filter(call: CallbackQuery, state: FSMContext):
    """
    Цикл значений: None -> True -> False -> None
    """
    key = call.data.split(":", 2)[2]
    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()

    curr = getattr(seg, key if key != "subs" else "subscribed")
    nxt = True if curr is None else (False if curr is True else None)

    if key == "subs":
        seg.subscribed = nxt
    elif key == "registered":
        seg.registered = nxt
    elif key == "access":
        seg.access_ok = nxt
    elif key == "vip":
        seg.vip = nxt

    await state.update_data(seg=seg)
    await call.answer()
    await _render_one(call, _fmt_segment(seg), kb_segment(seg))


@router.callback_query(F.data == "bc:next:text")
async def proceed_to_text(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()
    n = await _count_audience(seg)
    await state.set_state(BC.waiting_text)
    await call.answer()
    await _render_one(
        call,
        f"<b>Текст сообщения</b>\n\nАудитория (оценка): <b>{n}</b>\n\nПришли текст (HTML разрешён).",
        kb_text_stage(),
    )


# ========= Текст и картинка =========

@router.message(BC.waiting_text)
async def input_text(m: Message, state: FSMContext):
    txt = (m.html_text or m.text or "").strip()
    if not txt:
        await m.answer("Пустой текст. Пришли сообщение ещё раз.")
        return
    await state.update_data(text=txt)
    await _render_one(m, "<b>Текст сохранён.</b>\nМожно добавить картинку или перейти к кнопке.", kb_text_stage())


@router.callback_query(F.data == "bc:add:media")
async def ask_media(call: CallbackQuery, state: FSMContext):
    await state.set_state(BC.waiting_media)
    await call.answer()
    await _render_one(call, "Пришли фото (как фото). Либо нажми «Пропустить».", kb_media_stage())


@router.message(BC.waiting_media)
async def input_media(m: Message, state: FSMContext):
    if not m.photo:
        await m.answer("Это не фото. Пришли изображение (как фото).")
        return
    file_id = m.photo[-1].file_id
    await state.update_data(media=file_id)
    await _render_one(m, "Фото сохранено. Переходим к кнопке.", kb_button_stage())


@router.callback_query(F.data == "bc:skip:media")
async def skip_media(call: CallbackQuery, state: FSMContext):
    await state.update_data(media=None)
    await call.answer("Картинка пропущена.", show_alert=False)
    await _render_one(call, "Опциональная кнопка ниже.", kb_button_stage())


@router.callback_query(F.data == "bc:back:text")
async def back_to_text(call: CallbackQuery, state: FSMContext):
    await state.set_state(BC.waiting_text)
    await call.answer()
    await _render_one(call, "Отправь новый текст, либо нажми «Дальше → Кнопка».", kb_text_stage())


# ========= Кнопка =========

@router.callback_query(F.data == "bc:next:button")
async def to_button(call: CallbackQuery, state: FSMContext):
    await state.set_state(BC.waiting_button)
    await call.answer()
    await _render_one(
        call,
        "Пришли кнопку в формате:\n<b>Текст кнопки | https://ссылка</b>\n\n"
        "Например: <code>Открыть мини-апп | https://example.com</code>\n"
        "Или нажми «Пропустить кнопку».",
        kb_button_stage()
    )


@router.callback_query(F.data == "bc:add:button")
async def edit_button(call: CallbackQuery, state: FSMContext):
    await state.set_state(BC.waiting_button)
    await call.answer()
    await _render_one(call, "Пришли заново: <b>Текст | URL</b>.", kb_button_stage())


@router.callback_query(F.data == "bc:skip:button")
async def skip_button(call: CallbackQuery, state: FSMContext):
    await state.update_data(btn_text=None, btn_url=None)
    await call.answer("Кнопки не будет.", show_alert=False)
    await _render_one(call, "Готово. Можно перейти к предпросмотру.", kb_preview())


@router.message(BC.waiting_button)
async def input_button(m: Message, state: FSMContext):
    raw = (m.text or "").strip()
    if "|" not in raw:
        await m.answer("Нужно в формате: <b>Текст | https://ссылка</b>")
        return
    btn_text, btn_url = [x.strip() for x in raw.split("|", 1)]
    if not btn_text or not (btn_url.startswith("http://") or btn_url.startswith("https://")):
        await m.answer("URL должен начинаться с http:// или https://. Пришли снова.")
        return
    await state.update_data(btn_text=btn_text, btn_url=btn_url)
    await _render_one(m, f"Кнопка сохранена: «{btn_text}». Перейти к предпросмотру?", kb_preview())


# ========= Предпросмотр =========

@router.callback_query(F.data == "bc:back:segment")
async def back_to_segment(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()
    await state.set_state(BC.picking_segment)
    await call.answer()
    await _render_one(call, _fmt_segment(seg), kb_segment(seg))


@router.callback_query(F.data == "bc:next:preview")
async def do_preview(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()
    txt: str = data.get("text") or ""
    media: Optional[str] = data.get("media")
    btxt: Optional[str] = data.get("btn_text")
    burl: Optional[str] = data.get("btn_url")

    if not txt:
        await call.answer("Сначала введи текст.", show_alert=True)
        return

    n = await _count_audience(seg)
    await state.set_state(BC.confirming)

    info = (
        "<b>Предпросмотр</b>\n\n"
        f"Сегмент: {seg.pretty()}\n"
        f"Аудитория (оценка): <b>{n}</b>\n"
        f"Кнопка: {'есть' if btxt and burl else 'нет'}\n\n"
        "Ниже — как получит пользователь:"
    )
    await _render_one(call, info, kb_preview())

    markup = _kb_user_button(btxt, burl)
    if media:
        await call.message.answer_photo(media, caption=txt, reply_markup=markup)
    else:
        await call.message.answer(txt, reply_markup=markup)


# ========= Отправка =========

async def _send_to_user(bot, uid: int, txt: str, media: Optional[str], btn_text: Optional[str], btn_url: Optional[str]) -> bool:
    try:
        markup = _kb_user_button(btn_text, btn_url)
        if media:
            await bot.send_photo(uid, media, caption=txt, reply_markup=markup)
        else:
            await bot.send_message(uid, txt, reply_markup=markup)
        return True
    except Exception:
        return False


async def _list_ids(seg: Segment) -> List[int]:
    return await _list_audience(seg)


@router.callback_query(F.data == "bc:send")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != settings.ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    seg: Segment = data.get("seg") or Segment()
    txt: str = data.get("text") or ""
    media: Optional[str] = data.get("media")
    btn_text: Optional[str] = data.get("btn_text")
    btn_url: Optional[str] = data.get("btn_url")

    if not txt:
        await call.answer("Нет текста.", show_alert=True)
        return

    ids = await _list_ids(seg)
    total = len(ids)
    if total == 0:
        await call.answer("Аудитория пуста.", show_alert=True)
        return

    await call.answer("Старт.", show_alert=False)
    await _render_one(call, f"Отправляем {total} пользователям…", InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Идёт отправка…", callback_data="admin:back")]
    ]))

    sent = 0
    ok = 0
    batch = 25
    pause = 1.0

    for i in range(0, total, batch):
        chunk = ids[i:i + batch]
        results = await asyncio.gather(*[
            _send_to_user(call.message.bot, uid, txt, media, btn_text, btn_url) for uid in chunk
        ], return_exceptions=True)
        ok += sum(1 for r in results if r is True)
        sent += len(chunk)
        try:
            await call.message.edit_text(
                f"Рассылка… {sent}/{total}\nУспешно: {ok}\nНе доставлено: {sent - ok}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⏳ Идёт отправка…", callback_data="admin:back")]
                ]),
                disable_web_page_preview=True
            )
        except Exception:
            pass
        await asyncio.sleep(pause)

    await state.clear()
    await _render_one(call, f"Готово ✅\nУспешно: {ok}\nНе доставлено: {total - ok}", InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:back")]
    ]))
