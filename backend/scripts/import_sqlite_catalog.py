#!/usr/bin/env python3
"""Import books and students from a SQLite file into Libris PostgreSQL.

Dry-run is the default. Review the source schema first with inspect_sqlite_db.py.
Use --apply only after checking the mapping and taking a PostgreSQL backup.
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models import Book, BookCopy, Student

BOOK_TABLES = {"books", "book", "livros", "livro", "acervo", "catalogo", "catalog"}
STUDENT_TABLES = {"students", "student", "alunos", "aluno", "estudantes", "estudante"}
ALIASES = {
    "title": ("title", "titulo", "título", "nome_livro", "livro", "nome"),
    "author": ("author", "autor", "autoria", "escritor"),
    "category": ("category", "categoria", "genero", "gênero", "assunto", "classificacao", "classificação"),
    "isbn": ("isbn", "codigo_isbn", "código_isbn"),
    "publisher": ("publisher", "editora", "editor"),
    "year": ("publication_year", "year", "ano", "ano_publicacao", "ano_publicação"),
    "description": ("description", "descricao", "descrição", "sinopse"),
    "copies": ("copies", "exemplares", "quantidade", "qtd", "quantidade_exemplares"),
    "enrollment": ("enrollment_number", "matricula", "matrícula", "registro", "codigo_aluno", "código_aluno"),
    "student_name": ("full_name", "nome_completo", "nome", "aluno", "estudante", "name"),
}


def norm(s: str) -> str:
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def find_col(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    by_norm = {norm(c): c for c in columns}
    return next((by_norm[norm(a)] for a in aliases if norm(a) in by_norm), None)


def rows_for(conn: sqlite3.Connection, table: str) -> tuple[list[str], list[dict[str, Any]]]:
    qtable = '"' + table.replace('"', '""') + '"'
    cur = conn.execute(f"SELECT * FROM {qtable}")
    columns = [d[0] for d in cur.description or []]
    return columns, [dict(zip(columns, row)) for row in cur.fetchall()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Source SQLite .db/.sqlite file")
    parser.add_argument("--apply", action="store_true", help="Write records to PostgreSQL (otherwise dry-run)")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"File not found: {args.database}")

    source = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    source.row_factory = None
    imported = {"books": 0, "students": 0, "skipped": 0}
    try:
        tables = [r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        book_tables = [t for t in tables if norm(t) in BOOK_TABLES]
        student_tables = [t for t in tables if norm(t) in STUDENT_TABLES]
        if not book_tables and not student_tables:
            raise SystemExit("No recognized book/student tables. Run inspect_sqlite_db.py and map the source schema before importing.")
        db = SessionLocal()
        try:
            for table in book_tables:
                cols, rows = rows_for(source, table)
                mapping = {key: find_col(cols, ALIASES[key]) for key in ("title", "author", "category", "isbn", "publisher", "year", "description", "copies")}
                if not mapping["title"] or not mapping["author"]:
                    print(f"SKIP TABLE {table}: missing title/name or author column; needs manual mapping.")
                    continue
                for row in rows:
                    title = str(row.get(mapping["title"]) or "").strip()
                    author = str(row.get(mapping["author"]) or "").strip()
                    if not title or not author:
                        imported["skipped"] += 1
                        continue
                    isbn = str(row.get(mapping["isbn"]) or "").strip() if mapping["isbn"] else ""
                    if isbn and db.scalar(select(Book.id).where(Book.isbn == isbn)):
                        imported["skipped"] += 1
                        continue
                    category = str(row.get(mapping["category"]) or "Não classificado").strip() if mapping["category"] else "Não classificado"
                    try:
                        copies = max(1, min(1000, int(row.get(mapping["copies"]) or 1))) if mapping["copies"] else 1
                    except (ValueError, TypeError):
                        copies = 1
                    try:
                        year = int(row[mapping["year"]]) if mapping["year"] and row.get(mapping["year"]) not in (None, "") else None
                    except (ValueError, TypeError):
                        year = None
                    book = Book(title=title[:300], author=author[:200], category=category[:100], isbn=(isbn[:20] or None),
                                publisher=(str(row.get(mapping["publisher"]) or "").strip()[:160] or None) if mapping["publisher"] else None,
                                publication_year=year, description=(str(row.get(mapping["description"]) or "").strip() or None) if mapping["description"] else None)
                    if args.apply:
                        db.add(book)
                        try:
                            db.flush()
                            for i in range(1, copies + 1):
                                db.add(BookCopy(book_id=book.id, barcode=f"IMP-{book.id:07d}-{i:04d}"))
                            db.flush()
                        except IntegrityError:
                            db.rollback()
                            imported["skipped"] += 1
                            continue
                    imported["books"] += 1

            for table in student_tables:
                cols, rows = rows_for(source, table)
                name_col = find_col(cols, ALIASES["student_name"])
                enrollment_col = find_col(cols, ALIASES["enrollment"])
                if not name_col or not enrollment_col:
                    print(f"SKIP TABLE {table}: needs student name and enrollment/matricula columns; no synthetic enrollment is generated.")
                    continue
                for row in rows:
                    name = str(row.get(name_col) or "").strip()
                    enrollment = str(row.get(enrollment_col) or "").strip()
                    if not name or not enrollment:
                        imported["skipped"] += 1
                        continue
                    if db.scalar(select(Student.id).where(Student.enrollment_number == enrollment)):
                        imported["skipped"] += 1
                        continue
                    if args.apply:
                        db.add(Student(full_name=name[:160], enrollment_number=enrollment[:64]))
                        try:
                            db.flush()
                        except IntegrityError:
                            db.rollback()
                            imported["skipped"] += 1
                            continue
                    imported["students"] += 1
            if args.apply:
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    finally:
        source.close()
    mode = "APPLIED" if args.apply else "DRY RUN — NOTHING WRITTEN"
    print(f"\n{mode}\nBooks: {imported['books']}\nStudents: {imported['students']}\nSkipped/duplicate/incomplete: {imported['skipped']}")
    if not args.apply:
        print("Review the mapping and back up PostgreSQL before rerunning with --apply.")


if __name__ == "__main__":
    main()
