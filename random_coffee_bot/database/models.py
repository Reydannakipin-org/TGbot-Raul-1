from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, Column, Integer,
                        DateTime, Date, ForeignKey, String, Text)
from sqlalchemy.orm import DeclarativeBase, declared_attr, relationship


class Base(DeclarativeBase):
    pass


class CommonMixin:

    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = Column(Integer, primary_key=True)


class User(CommonMixin, Base):
    """Таблица пользователя."""

    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_in_group = Column(Boolean, default=True, nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    pairing_interval = Column(Integer, nullable=True)  # индивидуальный интервал (в днях)
    last_paired_at = Column(Date, nullable=True)
    pause_until = Column(Date, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Pair(CommonMixin, Base):
    """Таблица пар."""

    user1_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    user2_id = Column(Integer, ForeignKey('user.id'), nullable=False)

    paired_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user1 = relationship(
        "User", foreign_keys=[user1_id], back_populates="pairs_as_user1"
        )
    user2 = relationship(
        "User", foreign_keys=[user2_id], back_populates="pairs_as_user2"
        )

    feedbacks = relationship(
        "Feedback", back_populates="pair", cascade="all, delete"
        )


class Feedback(CommonMixin, Base):
    """Таблица с обратной связью."""

    pair_id = Column(Integer, ForeignKey('pair.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

    did_meet = Column(Boolean, default=False, nullable=True)
    comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    pair = relationship("Pair", back_populates="feedbacks")
    user = relationship("User", back_populates="feedbacks")


class Setting(CommonMixin, Base):
    """Таблица для изменяемых настроек работы бота."""

    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)
