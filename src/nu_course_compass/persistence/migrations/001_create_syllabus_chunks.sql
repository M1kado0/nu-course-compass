CREATE TABLE syllabus_chunks (
    chunk_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    search_vector TSVECTOR
        GENERATED ALWAYS AS (
            to_tsvector('english', content)
        ) STORED
);

CREATE INDEX syllabus_chunks_search_idx
    ON syllabus_chunks USING GIN (search_vector);

CREATE INDEX syllabus_chunks_course_idx
    ON syllabus_chunks ((metadata->>'course_code'));

CREATE INDEX syllabus_chunks_semester_idx
    ON syllabus_chunks ((metadata->>'semester'));