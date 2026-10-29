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
    # The physical-inventory schema is present after both fresh setup and legacy migration.
    assert "last_inventory_at" in {row["name"] for row in connection.execute("PRAGMA table_info(books)")}
    assert connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_scans'").fetchone()
    connection.execute("INSERT INTO readers(id,name,registration,phone,class_name,reading_goal) VALUES(2,'Outro leitor','ALU-002','','5º ano',12)")
    connection.execute("INSERT INTO reservations(book_id,reader_id,request_date,status) VALUES(2,1,'2026-10-28','Disponível para retirada')")
    assert app.find_available_copy(connection, "9780000000001", reader_id=2) is None
    held_for_reader = app.find_available_copy(connection, "9780000000001", reader_id=1)
    assert held_for_reader is not None and held_for_reader["accession_code"] == "LIB-SECOND"

# Exercise the mobile search/loan endpoints without opening a GUI or server port.
from datetime import date, datetime, timedelta
client = app.make_web().test_client()
search_response = client.get("/api/book?q=9780000000001")
assert search_response.status_code == 200
assert any(row["accession_code"] == "LIB-SECOND" for row in search_response.get_json()["books"])
blocked_response = client.post("/api/mobile-loan", json={
    "isbn": "9780000000001",
    "registration": "ALU-002",
    "due": (date.today() + timedelta(days=7)).isoformat(),
})
assert blocked_response.status_code == 409, blocked_response.get_json()
loan_response = client.post("/api/mobile-loan", json={
    "isbn": "9780000000001",
    "registration": "ALU-001",
    "due": (date.today() + timedelta(days=7)).isoformat(),
})
assert loan_response.status_code == 200, loan_response.get_json()
assert "LIB-SECOND" in loan_response.get_json()["message"]
with app.connect() as connection:
    active_count = connection.execute(
        "SELECT COUNT(*) FROM loans WHERE reader_id=1 AND returned_at IS NULL"
    ).fetchone()[0]
    assert active_count == 2
    reservation = connection.execute("SELECT status FROM reservations WHERE book_id=2 AND reader_id=1").fetchone()
    assert reservation["status"] == "Atendida"
    stamp = datetime.now().isoformat(timespec="seconds")
    connection.execute("UPDATE books SET last_inventory_at=? WHERE accession_code='LIB-SECOND'", (stamp,))
    book_id = connection.execute("SELECT id FROM books WHERE accession_code='LIB-SECOND'").fetchone()[0]
    connection.execute("INSERT INTO inventory_scans(book_id,scanned_at,condition_status) VALUES(?,?,?)", (book_id,stamp,"Bom"))
    assert connection.execute("SELECT COUNT(*) FROM inventory_scans WHERE book_id=?", (book_id,)).fetchone()[0] == 1

print("OK: migração, ISBN duplicado, reservas, limite de circulação, inventário e APIs mobile passaram.")
