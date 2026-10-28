"""Simple, persistent mapping between a student and their login account."""
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StudentAccount(Base):
    __tablename__ = "student_accounts"
    __table_args__ = (
        UniqueConstraint("student_id", name="uq_student_accounts_student"),
        UniqueConstraint("user_id", name="uq_student_accounts_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
