"""Synchronize Smart Tutor SQLite databases without overwriting divergent data."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "backend" / "app" / "smart_tutor.db"
DEFAULT_TARGET = PROJECT_ROOT / "backend" / "smart_tutor.db"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
              AND name != 'alembic_version'
            ORDER BY name
            """
        )
    ]


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        row[1]
        for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})")
    ]


def fetch_rows(
    connection: sqlite3.Connection, table: str, columns: list[str]
) -> list[tuple[object, ...]]:
    column_sql = ", ".join(quote_identifier(column) for column in columns)
    return connection.execute(
        f"SELECT {column_sql} FROM {quote_identifier(table)}"
    ).fetchall()


def synchronize(source_path: Path, target_path: Path) -> list[tuple[str, int]]:
    source_path = source_path.resolve()
    target_path = target_path.resolve()
    if source_path == target_path:
        raise ValueError("Source and target databases must be different files")
    if not source_path.is_file() or not target_path.is_file():
        raise FileNotFoundError("Both source and target database files must exist")

    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.execute("BEGIN")
        source_tables = table_names(source)
        if source_tables != table_names(target):
            raise RuntimeError("Source and target table sets differ")

        source_rows: dict[str, tuple[list[str], list[tuple[object, ...]]]] = {}
        for table in source_tables:
            source_columns = table_columns(source, table)
            target_columns = table_columns(target, table)
            if set(source_columns) != set(target_columns):
                raise RuntimeError(f"Column sets differ for table: {table}")

            # Select in target column order to handle databases created by
            # different migration histories with different physical ordering.
            source_rows[table] = (target_columns, fetch_rows(source, table, target_columns))

        target.execute("BEGIN IMMEDIATE")
        result: list[tuple[str, int]] = []
        try:
            for table, (columns, rows) in source_rows.items():
                if rows:
                    column_sql = ", ".join(quote_identifier(column) for column in columns)
                    placeholders = ", ".join("?" for _ in columns)
                    target.executemany(
                        f"INSERT OR IGNORE INTO {quote_identifier(table)} "
                        f"({column_sql}) VALUES ({placeholders})",
                        rows,
                    )

                target_rows = fetch_rows(target, table, columns)
                if set(rows) != set(target_rows) or len(rows) != len(target_rows):
                    raise RuntimeError(
                        f"Data conflict detected while synchronizing table: {table}"
                    )
                result.append((table, len(rows)))

            target.commit()
        except Exception:
            target.rollback()
            raise
    finally:
        source.rollback()
        source.close()
        target.close()

    return result


def mirror(source_path: Path, target_path: Path) -> list[tuple[str, int]]:
    """Replace target with a consistent SQLite backup of source."""
    source_path = source_path.resolve()
    target_path = target_path.resolve()
    if source_path == target_path:
        raise ValueError("Source and target databases must be different files")
    if not source_path.is_file() or not target_path.is_file():
        raise FileNotFoundError("Both source and target database files must exist")

    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()

    with sqlite3.connect(target_path) as target:
        return [
            (table, target.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0])
            for table in table_names(target)
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--mirror-target",
        action="store_true",
        help="Replace the target with a source snapshot after creating --backup.",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        help="Required with --mirror-target; path for the original target database.",
    )
    args = parser.parse_args()

    if args.mirror_target:
        if args.backup is None:
            parser.error("--backup is required with --mirror-target")
        backup_path = args.backup.resolve()
        if backup_path.exists():
            parser.error(f"Backup already exists: {backup_path}")
        if backup_path == args.source.resolve() or backup_path == args.target.resolve():
            parser.error("Backup path must be different from source and target")
        shutil.copy2(args.target.resolve(), backup_path)
        results = mirror(args.source, args.target)
        print(f"Target backup created at: {backup_path}")
    else:
        if args.backup is not None:
            parser.error("--backup can only be used with --mirror-target")
        results = synchronize(args.source, args.target)

    copied = [(table, count) for table, count in results if count]
    print(f"Synchronized {len(results)} tables: {copied}")


if __name__ == "__main__":
    main()
