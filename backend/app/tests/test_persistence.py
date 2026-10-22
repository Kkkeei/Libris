from sqlalchemy import select

from app.models.book import Book
from app.models.book_copy import BookCopy


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
    from sqlalchemy.exc import IntegrityError

    book = Book(title="Outro livro", author="Autoria fictícia", category="Literatura")
    db_session.add(book)
    db_session.flush()
    db_session.add_all([
        BookCopy(book_id=book.id, barcode="BARCODE-DUP"),
        BookCopy(book_id=book.id, barcode="BARCODE-DUP"),
    ])

    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("O banco deveria rejeitar código de barras duplicado.")
