from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from config import set

DATABASE_URL = set.database_url
print("DATABASE_URL = ", DATABASE_URL)

# Создаем асинхронный движок и сессию
engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession
)

Base = declarative_base()
