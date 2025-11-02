from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMember, ChatMemberAdministrator, ChatMemberOwner

from app.config import settings
from app.db.session import async_session
from app.models.user import User


def _is_member(cm: ChatMember) -> bool:
    """
    Возвращает True, если пользователь подписан на канал.
    Для каналов считаем подпиской статусы: member / administrator / creator (owner).
    """
    # aiogram v3 типы: ChatMemberOwner (creator), ChatMemberAdministrator, ChatMemberMember
    if isinstance(cm, (ChatMemberAdministrator, ChatMemberOwner)):
        return True

    status = getattr(cm, "status", None) or ""
    return str(status) in {"member", "administrator", "creator"}


async def verify_and_cache(bot: Bot, tg_id: int, channel_id: int | None, *, set_if_disabled: bool = True) -> bool:
    """
    Проверяет подписку на ОДИН канал (если он задан) и кеширует результат в users.is_subscribed.

    Возвращает True/False — актуальный статус подписки.
    """
    # Если шаг подписки выключен или канал не задан — считаем подписку пройденной
    if not settings.REQUIRE_SUBSCRIPTION or not channel_id:
        if set_if_disabled:
            async with async_session() as session:
                u = await session.get(User, tg_id)
                if not u:
                    u = User(id=tg_id)
                    session.add(u)
                    await session.flush()
                u.is_subscribed = True
                await session.commit()
        return True

    ok = False
    try:
        cm = await bot.get_chat_member(chat_id=channel_id, user_id=tg_id)
        ok = _is_member(cm)
    except TelegramBadRequest:
        # Бот не админ в канале/канал скрыт/не верный id — подписку считаем НЕпройденной
        ok = False
    except Exception:
        ok = False

    async with async_session() as session:
        u = await session.get(User, tg_id)
        if not u:
            u = User(id=tg_id)
            session.add(u)
            await session.flush()
        u.is_subscribed = ok
        await session.commit()

    return ok
