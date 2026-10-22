#!/usr/bin/env python3
"""Inspect a supplied SQLite .db/.sqlite file without printing personal records."""
import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to the source .db/.sqlite file")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"File not found: {args.database}")
    conn = sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True)
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        if not tables:
            print("No user tables found.")
            return
        for (table,) in tables:
            # Table names come from sqlite_master and are quoted by doubling quotes.
            quoted = '"' + table.replace('"', '""') + '"'
            columns = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            count = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            print(f"\nTABLE: {table} | ROWS: {count}")
            for col in columns:
                print(f"  - {col[1]} ({col[2] or 'unspecified'}){' PK' if col[5] else ''}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
