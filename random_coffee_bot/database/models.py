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
    has_permission = Column(Boolean, default=True, nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    pairing_interval = Column(Integer, nullable=True)
    last_paired_at = Column(Date, nullable=True)
    future_meeting = Column(Integer, default=1)
    pause_until = Column(Date, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    pairs_as_user1 = relationship(
        "Pair",
        foreign_keys="Pair.user1_id",
        back_populates="user1"
    )
    pairs_as_user2 = relationship(
        "Pair",
        foreign_keys="Pair.user2_id",
        back_populates="user2"
    )
    pairs_as_user3 = relationship(
        "Pair",
        foreign_keys="Pair.user3_id",
        back_populates="user3"
    )

    feedbacks = relationship("Feedback", back_populates="user")


class Pair(CommonMixin, Base):
    """Таблица пар."""

    user1_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    user2_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    user3_id = Column(Integer, ForeignKey('user.id'), nullable=True)

    feedback_sent = Column(Boolean, default=False)
    paired_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user1 = relationship(
        "User", foreign_keys=[user1_id], back_populates="pairs_as_user1"
    )
    user2 = relationship(
        "User", foreign_keys=[user2_id], back_populates="pairs_as_user2"
    )
    user3 = relationship(
        "User", foreign_keys=[user3_id], back_populates="pairs_as_user3"
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


class Setting(Base):
    """Таблица для изменяемых настроек работы бота."""
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False, default="global_interval")
    value = Column(Integer, nullable=False, default=2)
    first_matching_date = Column(DateTime, default=datetime(2025, 5, 15, 10, 0))


class Notification(CommonMixin, Base):
    """Таблица для текстов рассылки от админа."""

    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)
