import os
import uuid

from langchain_core.documents import Document
import psycopg
from psycopg import sql
import pytest

from nu_course_compass.ingestion.import_syllabus_chunks import import_chunks
from nu_course_compass.persistence.migrate import apply_migrations
from nu_course_compass.retrieval.syllabus_search import SearchResult, format_result, search


def test_empty_question_does_not_connect():
    assert search("   ") == []


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limits_fail_before_connecting(limit):
    with pytest.raises(ValueError, match="positive integer"):
        search("grading", limit=limit)


@pytest.fixture
def database():
    url = os.getenv("NU_COMPASS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NU_COMPASS_TEST_DATABASE_URL to a disposable test database")
    schema = "search_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        try:
            apply_migrations(conn)
            records = []
            for index in range(6):
                records.append({"page_content": "Grading policy: the final exam contributes 40 percent.",
                                "metadata": {"document_id": f"{index:064x}",
                                             "course_code": "BUS 101" if index < 3 else "CSCI 101",
                                             "semester": "Fall 2026" if index % 2 == 0 else "Spring 2026",
                                             "source_url": "https://example.org/syllabus",
                                             "retrieved_at": "2026-09-30T12:00:00+05:00",
                                             "page": index + 1}})
            records.append({"page_content": "Grading grading grading grading.",
                            "metadata": {"document_id": "f" * 64, "course_code": "MATH 101",
                                         "semester": "Fall 2026", "source_url": "https://example.org/word",
                                         "retrieved_at": "2026-09-30T12:00:00+05:00",
                                         "block_start": 4, "block_end": 6}})
            import_chunks(conn, records)
            yield conn
        finally:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_grading_returns_five_ranked_documents_with_stable_ties(database):
    results = search("grading", connection=database)
    assert len(results) == 5
    assert all(isinstance(result.document, Document) for result in results)
    assert results[0].document.id == "f" * 64
    assert results[0].score > results[1].score
    assert [r.document.id for r in results[1:]] == [f"{i:064x}" for i in range(4)]
    assert "<<Grading>>" in results[1].excerpt
    assert results[1].document.page_content == "Grading policy: the final exam contributes 40 percent."
    assert results == search("grading", connection=database)


def test_filters_are_applied_before_limit(database):
    results = search("grading", course_code="CSCI 101", semester="Spring 2026", limit=1, connection=database)
    assert len(results) == 1
    assert results[0].document.metadata["course_code"] == "CSCI 101"
    assert results[0].document.metadata["semester"] == "Spring 2026"
    assert search("grading", course_code="MISSING 999", connection=database) == []


def test_stemming_phrase_and_no_evidence(database):
    assert len(search("grade", connection=database)) == 5
    assert len(search('"final exam"', connection=database)) == 5
    assert search('"exam final"', connection=database) == []
    assert search("the and of", connection=database) == []
    assert search("nonexistentterm", connection=database) == []


def test_user_input_cannot_execute_sql(database):
    search("'; DROP TABLE syllabus_chunks; --", connection=database)
    assert search("grading", course_code="BUS 101' OR TRUE --", connection=database) == []
    assert database.execute("SELECT count(*) FROM syllabus_chunks").fetchone() == (7,)


def test_display_preserves_pdf_and_docx_citation_locations(database):
    results = search("grading", connection=database)
    docx = format_result(results[0], 1)
    pdf = format_result(results[1], 2)
    assert "MATH 101 | Fall 2026 | blocks 4–6" in docx
    assert "page" not in docx
    assert "BUS 101 | Fall 2026 | page 1" in pdf
    assert "https://example.org/syllabus" in pdf
    assert "2026-09-30T12:00:00+05:00" in pdf
