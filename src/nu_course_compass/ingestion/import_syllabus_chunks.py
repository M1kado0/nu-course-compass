"""Validate local JSONL chunks and import them atomically into PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import psycopg
from psycopg.types.json import Jsonb


def insert_syllabus_record(conn: psycopg.Connection, chunk_id: str, content: str, metadata: dict) -> bool:
    """Return True for a new row; reject conflicting IDs without overwriting."""
    inserted = conn.execute(
        """
        INSERT INTO syllabus_chunks (chunk_id, content, metadata)
        VALUES (%s, %s, %s)
        ON CONFLICT (chunk_id) DO NOTHING
        RETURNING chunk_id
        """,
        (chunk_id, content, Jsonb(metadata)),
    ).fetchone()
    if inserted is not None:
        return True
    existing = conn.execute(
        "SELECT content = %s AND metadata = %s FROM syllabus_chunks WHERE chunk_id = %s",
        (content, Jsonb(metadata), chunk_id),
    ).fetchone()
    if existing != (True,):
        raise ValueError(f"Conflicting existing chunk: {chunk_id}")
    return False


def _validate_chunk(record: object) -> None:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    content = record.get("page_content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("page_content must be nonempty text")
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    for field in ("document_id", "source_url", "index_url", "course_code", "semester",
                  "sha256", "retrieved_at", "parser_version"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"metadata.{field} must be nonempty text")
    for field in ("document_id", "sha256"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", metadata[field]):
            raise ValueError(f"metadata.{field} must be 64 hexadecimal characters")
    for field in ("source_url", "index_url"):
        url = urlparse(metadata[field])
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError(f"metadata.{field} must be an HTTP(S) source URL without credentials")
    try:
        retrieved = datetime.fromisoformat(metadata["retrieved_at"])
    except ValueError as exc:
        raise ValueError("metadata.retrieved_at must be an ISO timestamp") from exc
    if retrieved.utcoffset() is None:
        raise ValueError("metadata.retrieved_at must include a timezone")

    def positive_integer(value: object) -> bool:
        return type(value) is int and value > 0

    if "page" in metadata:
        if not positive_integer(metadata["page"]):
            raise ValueError("metadata.page must be a positive integer")
        if "block_start" in metadata or "block_end" in metadata:
            raise ValueError("use page or DOCX block range, not both")
    elif not (positive_integer(metadata.get("block_start"))
              and positive_integer(metadata.get("block_end"))
              and metadata["block_start"] <= metadata["block_end"]):
        raise ValueError("metadata must include a positive page or ordered DOCX block range")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def read_chunks(path: Path, limit: int | None) -> list[dict]:
    """Validate all selected nonblank records before opening a database connection."""
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    chunks = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line, parse_constant=_reject_json_constant)
                _validate_chunk(record)
            except ValueError as exc:
                message = "invalid JSON" if isinstance(exc, json.JSONDecodeError) else str(exc)
                raise ValueError(f"Line {line_number}: {message}") from exc
            chunks.append(record)
            if limit is not None and len(chunks) == limit:
                break
    return chunks


def import_chunks(conn: psycopg.Connection, chunks: list[dict]) -> dict[str, int]:
    inserted = 0
    with conn.transaction():
        for chunk in chunks:
            inserted += insert_syllabus_record(conn, chunk["metadata"]["document_id"],
                                               chunk["page_content"], chunk["metadata"])
    return {"selected": len(chunks), "inserted": inserted, "unchanged": len(chunks) - inserted}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--limit", type=int, help="Positive chunk cap; omitted imports all records")

    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        chunks = read_chunks(args.input, args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    from nu_course_compass.persistence.connection import get_db_connection

    with get_db_connection() as conn:
        summary = import_chunks(conn, chunks)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
