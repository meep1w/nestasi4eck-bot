from __future__ import annotations

import secrets
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from app.db.session import async_session
from app.models.user import User
from app.config import settings


def _gen_click_id(tg_id: int) -> str:
    # компактный и читаемый click_id: <tgid>-<6*urlsafe>
    return f"{tg_id}-{secrets.token_urlsafe(6)}"


async def ensure_click_id(tg_id: int) -> str:
    """
    Гарантирует наличие user.click_id. Возвращает актуальный click_id.
    """
    async with async_session() as session:
        u: User | None = await session.get(User, tg_id)
        if not u:
            u = User(id=tg_id)
            session.add(u)
            await session.flush()

        if not u.click_id:
            u.click_id = _gen_click_id(tg_id)
            await session.commit()
        return u.click_id


def build_ref_link_with_click(click_id: str) -> str:
    """
    Подставляет click_id в REF_LINK, аккуратно добавляя/обновляя query-параметр.
    """
    base = settings.REF_LINK or ""
    if not base:
        return ""
    url = urlparse(base)
    q = dict(parse_qsl(url.query, keep_blank_values=True))
    q["click_id"] = click_id
    new_q = urlencode(q)
    return urlunparse((url.scheme, url.netloc, url.path, url.params, new_q, url.fragment))
