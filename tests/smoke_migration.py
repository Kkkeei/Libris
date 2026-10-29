"""Smoke test for migrating an existing Libris SQLite database without losing history."""
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

temporary_root = tempfile.mkdtemp(prefix="libris-smoke-")
os.environ["XDG_DATA_HOME"] = temporary_root
database_path = Path(temporary_root) / "libris" / "libris.db"
database_path.parent.mkdir(parents=True, exist_ok=True)

# Simulate a database created by the earlier Libris versions.
legacy = sqlite3.connect(database_path)
legacy.execute("PRAGMA foreign_keys=ON")
legacy.executescript("""
CREATE TABLE books(
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT DEFAULT '',
    isbn TEXT UNIQUE, category TEXT DEFAULT '', column_code TEXT DEFAULT '',
    shelf_row INTEGER
);
CREATE TABLE readers(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, registration TEXT UNIQUE,
    phone TEXT DEFAULT ''
);
CREATE TABLE loans(
    id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
    reader_id INTEGER NOT NULL REFERENCES readers(id), loan_date TEXT NOT NULL,
    due_date TEXT NOT NULL, returned_at TEXT
);
INSERT INTO books(id,title,author,isbn,category,column_code,shelf_row)
VALUES(1,'A Biblioteca da Meia-Noite','Matt Haig','9780000000001','Ficção','A',2);
INSERT INTO readers(id,name,registration,phone)
VALUES(1,'Leitor de Teste','ALU-001','');
INSERT INTO loans(id,book_id,reader_id,loan_date,due_date,returned_at)
VALUES(1,1,1,'2026-10-01','2026-10-15',NULL);
""")
legacy.commit()
legacy.close()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

app.init_db()
with app.connect() as connection:
    book = connection.execute("SELECT * FROM books WHERE id=1").fetchone()
    reader = connection.execute("SELECT * FROM readers WHERE id=1").fetchone()
    loan = connection.execute("SELECT * FROM loans WHERE id=1").fetchone()
    assert book is not None and book["title"] == "A Biblioteca da Meia-Noite"
    assert book["accession_code"] == "LIB-000001"
    assert book["condition_status"] == "Bom"
    assert reader is not None and reader["registration"] == "ALU-001"
    assert reader["class_name"] == ""
    assert loan is not None and loan["returned_at"] is None
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    # An ISBN may have more than one physical copy now, each with a distinct tomb.
    connection.execute(
        """INSERT INTO books(title,author,isbn,category,column_code,shelf_row,accession_code,condition_status)
           VALUES(?,?,?,?,?,?,?,?)""",
        ("A Biblioteca da Meia-Noite", "Matt Haig", "9780000000001",
         "Ficção", "A", 3, "LIB-SECOND", "Bom"),
    )
    available = app.find_available_copy(connection, "9780000000001")
    assert available is not None and available["accession_code"] == "LIB-SECOND"
    assert connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 0

print("OK: migração preservou livros, leitores e empréstimos; ISBN duplicado por exemplar foi validado.")
