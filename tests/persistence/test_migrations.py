import hashlib
import os
from pathlib import Path
import uuid

import psycopg
from psycopg import sql
import pytest

from nu_course_compass.persistence.migrate import apply_migrations, read_migrations


def test_packaged_sql_is_found_outside_project(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    migrations = read_migrations()
    assert migrations[0].filename == "001_create_syllabus_chunks.sql"
    assert "GENERATED ALWAYS AS" in migrations[0].sql


def test_numeric_order_and_exact_byte_checksum(tmp_path):
    for name in ("10_last.sql", "2_first.sql"):
        (tmp_path / name).write_text("SELECT 1;\n")
    migrations = read_migrations(tmp_path)
    assert [m.filename for m in migrations] == ["2_first.sql", "10_last.sql"]
    assert migrations[0].checksum == hashlib.sha256(b"SELECT 1;\n").hexdigest()


@pytest.mark.parametrize("name", ["first.sql", "001_duplicate.sql"])
def test_rejects_ambiguous_migration_names(tmp_path, name):
    (tmp_path / "001_original.sql").write_text("SELECT 1;")
    (tmp_path / name).write_text("SELECT 2;")
    with pytest.raises(ValueError):
        read_migrations(tmp_path)


@pytest.fixture
def database():
    url = os.getenv("NU_COMPASS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NU_COMPASS_TEST_DATABASE_URL to a dedicated disposable test database")
    schema = "migration_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        try:
            yield conn
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_applies_packaged_schema_and_skips_unchanged(database):
    assert apply_migrations(database) == ["001_create_syllabus_chunks.sql"]
    ledger = database.execute("SELECT filename, checksum, applied_at FROM schema_migrations").fetchall()
    assert ledger[0][1] == read_migrations()[0].checksum
    assert ledger[0][2] is not None
    assert apply_migrations(database) == []
    assert database.execute("SELECT filename, checksum, applied_at FROM schema_migrations").fetchall() == ledger
    database.execute("INSERT INTO syllabus_chunks (chunk_id, content, metadata) VALUES ('fixture', 'grading policies', '{}')")
    assert database.execute("SELECT search_vector @@ to_tsquery('english', 'grade') FROM syllabus_chunks").fetchone() == (True,)
    indexes = database.execute("SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()").fetchall()
    assert {row[0] for row in indexes} >= {"syllabus_chunks_search_idx", "syllabus_chunks_course_idx", "syllabus_chunks_semester_idx"}


def test_rejects_edited_applied_migration_before_pending_ddl(database, tmp_path):
    first = tmp_path / "001_first.sql"
    first.write_text("CREATE TABLE original (id INTEGER);")
    apply_migrations(database, tmp_path)
    first.write_text("CREATE TABLE original (id TEXT);")
    (tmp_path / "002_second.sql").write_text("CREATE TABLE pending (id INTEGER);")
    with pytest.raises(ValueError, match="checksum changed"):
        apply_migrations(database, tmp_path)
    assert database.execute("SELECT to_regclass('pending')").fetchone() == (None,)
    assert database.execute("SELECT count(*) FROM schema_migrations").fetchone() == (1,)


def test_failed_batch_rolls_back_ddl_and_ledger(database, tmp_path):
    (tmp_path / "001_good.sql").write_text("CREATE TABLE should_rollback (id INTEGER);")
    (tmp_path / "002_bad.sql").write_text("SELECT * FROM missing_table;")
    with pytest.raises(psycopg.errors.UndefinedTable):
        apply_migrations(database, tmp_path)
    assert database.execute("SELECT to_regclass('should_rollback'), to_regclass('schema_migrations')").fetchone() == (None, None)


def test_applies_custom_sql_in_numeric_order(database, tmp_path):
    (tmp_path / "2_create.sql").write_text("CREATE TABLE ordered (id INTEGER);")
    (tmp_path / "10_insert.sql").write_text("INSERT INTO ordered VALUES (1);")
    assert apply_migrations(database, tmp_path) == ["2_create.sql", "10_insert.sql"]
    assert database.execute("SELECT id FROM ordered").fetchone() == (1,)
