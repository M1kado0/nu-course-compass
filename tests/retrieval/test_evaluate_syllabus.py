import pytest

from nu_course_compass.retrieval.evaluate_syllabus import metrics, windows


def test_metrics():
    assert metrics({"a", "b"}, ["c", "b"] ) == {
        "recall_at_5": 0.5, "reciprocal_rank_at_5": 0.5, "hit_at_5": 1}
    assert metrics(set(), ["c"]) == {"returned_candidates": 1}


def test_windows_cover_without_truncation():
    values = list(range(600))
    parts = windows(values)
    assert max(map(len, parts)) == 254
    assert set(sum(parts, [])) == set(values)
    assert parts[0][-32:] == parts[1][:32]
    assert parts[-1][-1] == 599


def test_invalid_windows():
    with pytest.raises(ValueError):
        windows([])
    with pytest.raises(ValueError):
        windows([1], budget=32, overlap=32)
