from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.book import Book
from app.models.book_copy import BookCopy
from app.models.loan import Loan
from app.models.student import Student


def test_book_and_copy_persist_in_database(db_session):
    book = Book(title="Livro de teste", author="Autoria fictícia", category="Literatura")
    db_session.add(book)
    db_session.flush()
    copy = BookCopy(book_id=book.id, barcode="TEST-COPY-0001")
    db_session.add(copy)
    db_session.commit()

    saved_book = db_session.scalar(select(Book).where(Book.title == "Livro de teste"))
    saved_copy = db_session.scalar(select(BookCopy).where(BookCopy.barcode == "TEST-COPY-0001"))
    assert saved_book is not None
    assert saved_book.author == "Autoria fictícia"
    assert saved_copy is not None
    assert saved_copy.book_id == saved_book.id


def test_duplicate_copy_barcode_is_rejected(db_session):
    book = Book(title="Outro livro", author="Autoria fictícia", category="Literatura")
    db_session.add(book)
    db_session.flush()
    db_session.add_all([
        BookCopy(book_id=book.id, barcode="BARCODE-DUP"),
        BookCopy(book_id=book.id, barcode="BARCODE-DUP"),
    ])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sqlite_partial_index_prevents_duplicate_active_loan(db_session):
    student = Student(full_name="Aluno de teste", enrollment_number="REG-001")
    book = Book(title="Livro", author="Autoria", category="Teste")
    db_session.add_all([student, book])
    db_session.flush()
    copy = BookCopy(book_id=book.id, barcode="ONLY-COPY")
    db_session.add(copy)
    db_session.flush()
    db_session.add(Loan(student_id=student.id, copy_id=copy.id, due_date=date.today()+timedelta(days=7)))
    db_session.commit()

    db_session.add(Loan(student_id=student.id, copy_id=copy.id, due_date=date.today()+timedelta(days=7)))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
