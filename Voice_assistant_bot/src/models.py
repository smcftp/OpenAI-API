from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    values = relationship("UserValue", back_populates="owner")

class UserValue(Base):
    __tablename__ = "user_values"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    value = Column(Text, nullable=False)
    owner = relationship("User", back_populates="values")