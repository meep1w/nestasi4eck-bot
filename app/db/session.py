from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool
from app.config import settings

# Для SQLite в dev: echo=False, future=True. StaticPool полезен для in-memory,
# но для файла нам не нужен. Оставим дефолт.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Фабрика сессий
async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Удобный dependency-генератор (если понадобится в сервисах/роутерах)
async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
