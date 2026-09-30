import copy
import json
import os
import sys
import uuid

import psycopg
from psycopg import sql
import pytest

from nu_course_compass.ingestion.import_syllabus_chunks import import_chunks, main, read_chunks
from nu_course_compass.persistence.migrate import apply_migrations


def chunk(identifier="a" * 64):
    return {"page_content": "Grading: exam 40%, coursework 60%.", "metadata": {
        "document_id": identifier, "source_url": "https://example.org/syllabus.pdf",
        "index_url": "https://example.org/index", "course_code": "CSCI 101",
        "semester": "Fall 2026", "sha256": "b" * 64,
        "retrieved_at": "2026-09-30T12:00:00+05:00", "parser_version": "pymupdf-page-v1",
        "page": 2, "historical_source": True, "extra": {"original": [1, "two"]},
    }}


def write_chunks(tmp_path, records):
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    return path


def test_reads_all_or_limited_and_preserves_metadata(tmp_path):
    records = [chunk(), chunk("c" * 64)]
    path = write_chunks(tmp_path, records)
    assert read_chunks(path, None) == records
    assert read_chunks(path, 1) == records[:1]
    with path.open("a") as stream:
        stream.write("not JSON\n")
    assert read_chunks(path, 2) == records
    with pytest.raises(ValueError, match="Line 3: invalid JSON"):
        read_chunks(path, None)


@pytest.mark.parametrize(("field", "value"), [
    ("document_id", "short"), ("sha256", "z" * 64),
    ("source_url", "file:///private/file.pdf"), ("index_url", "https://u:p@example.org"),
    ("course_code", ""), ("semester", " "), ("parser_version", None),
    ("retrieved_at", "2026-09-30T12:00:00"), ("retrieved_at", "not a date"),
    ("page", 0), ("page", True), ("page", 1.5),
])
def test_invalid_metadata_has_physical_line_number(tmp_path, field, value):
    record = chunk()
    record["metadata"][field] = value
    path = write_chunks(tmp_path, [record])
    path.write_text("\n" + path.read_text())
    with pytest.raises(ValueError, match="Line 2:"):
        read_chunks(path, None)


@pytest.mark.parametrize("record", [None, [], {"page_content": "", "metadata": {}},
                                    {"page_content": "text", "metadata": []}])
def test_rejects_invalid_record_shapes(tmp_path, record):
    with pytest.raises(ValueError, match="Line 1:"):
        read_chunks(write_chunks(tmp_path, [record]), None)


def test_docx_requires_ordered_positive_blocks_without_page(tmp_path):
    record = chunk()
    del record["metadata"]["page"]
    record["metadata"].update(block_start=1, block_end=3)
    assert read_chunks(write_chunks(tmp_path, [record]), None) == [record]
    for start, end in ((0, 3), (3, 1), (True, 2), (1, None)):
        record["metadata"].update(block_start=start, block_end=end)
        with pytest.raises(ValueError, match="block range"):
            read_chunks(write_chunks(tmp_path, [record]), None)
    record["metadata"].update(page=1, block_start=1, block_end=2)
    with pytest.raises(ValueError, match="not both"):
        read_chunks(write_chunks(tmp_path, [record]), None)


def test_invalid_cli_input_does_not_open_connection(tmp_path, monkeypatch):
    from nu_course_compass.persistence import connection
    def unexpected_connection():
        pytest.fail("validation must happen before opening a connection")
    monkeypatch.setattr(connection, "get_db_connection", unexpected_connection)
    path = write_chunks(tmp_path, [chunk(), {}])
    monkeypatch.setattr(sys, "argv", ["import_syllabus_chunks", str(path)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.fixture
def database():
    url = os.getenv("NU_COMPASS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NU_COMPASS_TEST_DATABASE_URL to a disposable test database")
    schema = "chunk_import_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        try:
            apply_migrations(conn)
            yield conn
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_import_twice_skips_identical_rows_and_retains_json(database):
    records = [chunk(), chunk("c" * 64)]
    assert import_chunks(database, records) == {"selected": 2, "inserted": 2, "unchanged": 0}
    assert import_chunks(database, records) == {"selected": 2, "inserted": 0, "unchanged": 2}
    assert database.execute("SELECT content, metadata FROM syllabus_chunks WHERE chunk_id = %s",
                            (records[0]["metadata"]["document_id"],)).fetchone() == (
                                records[0]["page_content"], records[0]["metadata"])
    assert database.execute("SELECT count(*) FROM syllabus_chunks").fetchone() == (2,)


@pytest.mark.parametrize("changed_field", ["content", "metadata", "json_type"])
def test_conflict_rolls_back_prior_new_rows(database, changed_field):
    original = chunk()
    import_chunks(database, [original])
    changed = copy.deepcopy(original)
    if changed_field == "content":
        changed["page_content"] = "Different grading policy"
    elif changed_field == "metadata":
        changed["metadata"]["semester"] = "Spring 2026"
    else:
        # Python considers True == 1, but these are different JSONB values.
        changed["metadata"]["historical_source"] = 1
    with pytest.raises(ValueError, match="Conflicting existing chunk"):
        import_chunks(database, [chunk("c" * 64), changed])
    assert database.execute("SELECT chunk_id FROM syllabus_chunks").fetchall() == [("a" * 64,)]
    assert database.execute("SELECT metadata FROM syllabus_chunks").fetchone()[0] == original["metadata"]


def test_duplicates_in_same_batch_are_unchanged(database):
    assert import_chunks(database, [chunk(), chunk()]) == {"selected": 2, "inserted": 1, "unchanged": 1}
