from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Text

from src.database import Base

class UserValue(Base):
    __tablename__ = "user_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
