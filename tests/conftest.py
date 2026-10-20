import os

# До импорта приложения: settings читаются при импорте, тесты работают в отдельной базе.
os.environ['POSTGRES_DB'] = 'payment_test'

from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from core.config import settings  # noqa: E402
from db.postgres import async_session, engine  # noqa: E402
from main import app  # noqa: E402
from models import Base  # noqa: E402


async def _create_database() -> None:
    admin_url = settings.postgres.url.rsplit('/', 1)[0] + '/postgres'
    admin_engine = create_async_engine(admin_url, isolation_level='AUTOCOMMIT')
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text('SELECT 1 FROM pg_database WHERE datname = :name'),
            {'name': settings.postgres.db},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{settings.postgres.db}"'))
    await admin_engine.dispose()


@pytest.fixture(scope='session', autouse=True)
async def database() -> AsyncGenerator[None, None]:
    await _create_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables() -> None:
    # Каждый тест начинает с пустой базы и создаёт данные фабриками.
    async with engine.begin() as conn:
        await conn.execute(
            text('TRUNCATE payments, promo_codes, tariffs CASCADE')
        )


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as c:
        yield c
