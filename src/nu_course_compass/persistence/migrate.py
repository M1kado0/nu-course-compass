"""Apply packaged SQL migrations with immutable checksum tracking."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib.resources import files
from pathlib import Path
import re

import psycopg


@dataclass(frozen=True)
class Migration:
    filename: str
    checksum: str
    sql: str


def read_migrations(directory: Path | None = None) -> list[Migration]:
    """Read package resources by numeric prefix, independently of cwd."""
    root = directory if directory is not None else files(__package__).joinpath("migrations")
    numbered = []
    versions: set[int] = set()
    for resource in root.iterdir():
        if not resource.is_file() or not resource.name.endswith(".sql"):
            continue
        match = re.fullmatch(r"(\d+)_[A-Za-z0-9_]+\.sql", resource.name)
        if match is None:
            raise ValueError(f"Invalid migration filename: {resource.name}")
        version = int(match.group(1))
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        content = resource.read_bytes()
        numbered.append((version, Migration(resource.name, hashlib.sha256(content).hexdigest(),
                                            content.decode("utf-8"))))
    return [migration for _, migration in sorted(numbered, key=lambda entry: entry[0])]


def apply_migrations(conn: psycopg.Connection, directory: Path | None = None) -> list[str]:
    """Apply a batch atomically; errors roll back both DDL and ledger entries.

    SQL migrations must not contain transaction-control statements or operations
    such as CREATE INDEX CONCURRENTLY that cannot run inside a transaction.
    """
    migrations = read_migrations(directory)
    applied = []
    with conn.transaction():
        # Serialize competing runners before creating or reading the ledger.
        conn.execute("SELECT pg_advisory_xact_lock(684312570120)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing = dict(conn.execute("SELECT filename, checksum FROM schema_migrations").fetchall())
        available = {migration.filename: migration for migration in migrations}
        for filename, checksum in existing.items():
            if filename not in available:
                raise ValueError(f"Applied migration is missing: {filename}")
            if available[filename].checksum != checksum:
                raise ValueError(f"Applied migration checksum changed: {filename}")
        for migration in migrations:
            if migration.filename in existing:
                continue
            conn.execute(migration.sql)
            conn.execute("INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                         (migration.filename, migration.checksum))
            applied.append(migration.filename)
    return applied


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    from .connection import get_db_connection

    with get_db_connection() as conn:
        applied = apply_migrations(conn)
    for filename in applied:
        print(f"Applied: {filename}")
    if not applied:
        print("No pending migrations")


if __name__ == "__main__":
    main()
