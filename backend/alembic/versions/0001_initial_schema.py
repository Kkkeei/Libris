"""Initial Libris schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="librarian"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "school_classes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("school_year", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_school_classes_name", "school_classes", ["name"])
    op.create_index("ix_school_classes_school_year", "school_classes", ["school_year"])

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enrollment_number", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["school_classes.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("enrollment_number"),
    )
    op.create_index("ix_students_full_name", "students", ["full_name"])
    op.create_index("ix_students_class_id", "students", ["class_id"])

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("publisher", sa.String(length=160), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("isbn"),
    )
    for col in ("title", "author", "category"):
        op.create_index(f"ix_books_{col}", "books", [col])

    op.create_table(
        "book_copies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index("ix_book_copies_book_id", "book_copies", ["book_id"])

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("copy_id", sa.Integer(), nullable=False),
        sa.Column("loaned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("returned_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["copy_id"], ["book_copies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["returned_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for col in ("student_id", "copy_id", "loaned_at", "due_date", "returned_at", "status"):
        op.create_index(f"ix_loans_{col}", "loans", [col])
    op.create_index(
        "uq_loans_one_active_per_copy",
        "loans",
        ["copy_id"],
        unique=True,
        postgresql_where=sa.text("returned_at IS NULL"),
        sqlite_where=sa.text("returned_at IS NULL"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("loans")
    op.drop_table("book_copies")
    op.drop_table("books")
    op.drop_table("students")
    op.drop_table("school_classes")
    op.drop_table("users")
