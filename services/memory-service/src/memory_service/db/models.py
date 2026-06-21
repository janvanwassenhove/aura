"""SQLAlchemy ORM table definitions for the memory service."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TurnRow(Base):
    __tablename__ = "turns"

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String(32))


class TodoRow(Base):
    __tablename__ = "todos"

    todo_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(32))


class ReminderRow(Base):
    __tablename__ = "reminders"

    reminder_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    due_at: Mapped[str] = mapped_column(String(32))
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
