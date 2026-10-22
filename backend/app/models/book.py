from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    isbn: Mapped[str | None] = mapped_column(String(20), unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    publisher: Mapped[str | None] = mapped_column(String(160))
    publication_year: Mapped[int | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    copies: Mapped[list["BookCopy"]] = relationship(back_populates="book")
