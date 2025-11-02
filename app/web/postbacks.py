from __future__ import annotations

from typing import Optional

from aiohttp import web
from aiogram import Bot

from app.config import settings
from app.services.postbacks import apply_postback, send_postback_card

# авто-пуш
from app.db.session import async_session
from app.models.user import User
from app.services.postbacks import recompute_user_from_postbacks
from app.services.users import decide_next_step, mark_regular_once_shown, mark_vip_once_shown
from app.routers import checks, menu as menu_router


def _to_float(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "."))
    except Exception:
        return None


def _to_int(x: Optional[str]) -> Optional[int]:
    if x is None:
        return None
    try:
        return int(str(x).strip())
    except Exception:
        return None


from app.routers import checks as checks_router
from app.services.postbacks import recompute_user_from_postbacks
from app.db.session import async_session
from app.models.user import User

async def _auto_push_ui(bot: Bot, tg_id: int):
    async with async_session() as session:
        user: User | None = await session.get(User, tg_id)
        if not user:
            return

    try:
        await recompute_user_from_postbacks(tg_id)
    except Exception:
        pass

    # Теперь пушим именно следующий экран.
    try:
        await checks_router.push_next_screen(bot, tg_id)
    except Exception:
        # в крайнем случае ничего не ломаем
        pass


async def _handle_postback(request: web.Request) -> web.Response:
    secret_env = (settings.POSTBACK_HTTP_SECRET or "").strip()
    secret_got = (request.query.get("secret") or "").strip()
    if secret_env and secret_got != secret_env:
        return web.Response(text="forbidden", status=403)

    params = dict(request.query)
    if request.method == "POST":
        try:
            data = await request.post()
            for k, v in data.items():
                params.setdefault(k, v)
        except Exception:
            pass

    event = (params.get("event") or "").strip().lower()
    if event not in {"registration", "deposit_first", "deposit_repeat", "deposit"}:
        if "deposit" in event:
            event = "deposit"
        else:
            return web.Response(text="bad request: event", status=400)

    trader_id = (params.get("trader_id") or params.get("trader") or params.get("account") or "").strip() or None
    click_id = (params.get("click_id") or "").strip() or None

    tg_id = _to_int(params.get("tg_id") or params.get("user") or params.get("user_id"))  # опционально
    amount = _to_float(params.get("sumdep") or params.get("amount"))
    ts = _to_int(params.get("ts"))

    payload = {
        "event": event,
        "tg_id": tg_id,
        "trader_id": trader_id,
        "click_id": click_id,
        "amount_usd": amount,
        "ts": ts,
        "raw_text": f"event={event}; tg={tg_id}; trader={trader_id}; click={click_id}; amount={amount}; ts={ts}"
    }

    res = await apply_postback(payload)

    # карточка в канал
    try:
        bot: Bot = request.app["bot"]
        await send_postback_card(bot, res)
    except Exception:
        pass

    # автопуш только если знаем реальный tg_id пользователя
    if res.tg_id:
        try:
            bot: Bot = request.app["bot"]
            await _auto_push_ui(bot, res.tg_id)
        except Exception:
            pass

    return web.Response(text="ok", status=200)


def create_app(bot: Bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.add_routes([web.get("/postback", _handle_postback), web.post("/postback", _handle_postback)])
    return app


async def start_postback_server(bot: Bot):
    host = getattr(settings, "POSTBACK_HTTP_HOST", "0.0.0.0")
    port = int(getattr(settings, "POSTBACK_HTTP_PORT", 8080))
    app = create_app(bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
