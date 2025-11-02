from aiogram import Router

# Обработчики постбэков перенесены в aiohttp-сервер: app/web/postbacks.py
# Этот роутер оставляем пустым, чтобы его можно было подключать в main.py.
router = Router(name=__name__)
