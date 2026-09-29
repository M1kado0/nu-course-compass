"""Normalize the MOE syllabus index without treating it as course authority."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
SPREADSHEET_ID = "1R9a86iwqr7oDo60hZt6WQLPm0EDRXNTu5-r7vt0IKgU"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
EXPECTED_GIDS = frozenset(
    {
        408640312,
        1250760069,
        336758525,
        518227921,
        591735222,
        1677333311,
        2051753266,
        1087526584,
        1426814024,
        634347005,
        1676475718,
    }
)
HEADERS = ("course code", "instructor name", "semester", "link to syllabi")


@dataclass(frozen=True)
class SyllabusIndexRow:
    course_code: str
    instructor: str
    semester: str
    school: str
    syllabus_url: str
    sheet_title: str
    sheet_gid: int
    sheet_row: int

    @property
    def source_url(self) -> str:
        return f"{SHEET_URL}?gid={self.sheet_gid}#gid={self.sheet_gid}&range=B{self.sheet_row}:E{self.sheet_row}"

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self) | {"source_url": self.source_url}


@dataclass(frozen=True)
class SheetIssue:
    sheet_title: str
    sheet_row: int
    reason: str


def _value(cell: dict[str, object]) -> str:
    return str(cell.get("formattedValue") or "").strip()


def _link(cell: dict[str, object]) -> str:
    direct = cell.get("hyperlink")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    value = _value(cell)
    if value.startswith(("https://", "http://")):
        return value
    runs = cell.get("textFormatRuns") or []
    links = {
        run.get("format", {}).get("link", {}).get("uri")
        for run in runs
        if isinstance(run, dict)
    }
    links.discard(None)
    return next(iter(links)) if len(links) == 1 else ""


def parse_sheet_grid(
    *, sheet_title: str, sheet_gid: int, grid: dict[str, object]
) -> tuple[list[SyllabusIndexRow], list[SheetIssue]]:
    """Parse A:E grid data, including repeated school sections and headers."""
    rows: list[SyllabusIndexRow] = []
    issues: list[SheetIssue] = []
    current_school = ""
    header_start: int | None = None
    row_data = grid.get("rowData") or []
    if not isinstance(row_data, list):
        raise ValueError(f"Invalid rowData for {sheet_title}")

    for row_number, raw_row in enumerate(row_data, start=1):
        cells = raw_row.get("values", []) if isinstance(raw_row, dict) else []
        cells = cells if isinstance(cells, list) else []
        cells = [cell if isinstance(cell, dict) else {} for cell in cells]
        cells.extend({} for _ in range(max(0, 5 - len(cells))))
        values = [_value(cell) for cell in cells]
        if not any(values):
            continue

        header_positions = [
            start
            for start in range(max(0, len(values) - 3))
            if tuple(value.casefold() for value in values[start : start + 4])
            == HEADERS
        ]
        if header_positions:
            header_start = header_positions[0]
            continue

        nonempty = [value for value in values if value]
        if len(nonempty) == 1 and re.fullmatch(r"[A-Z]{2,8}", nonempty[0]):
            current_school = nonempty[0]
            continue
        if header_start is None:
            continue

        course_code, instructor, semester, _ = values[
            header_start : header_start + 4
        ]
        link = _link(cells[header_start + 3])
        if not course_code and not instructor and not semester and not link:
            continue
        if not course_code or not semester or not link:
            issues.append(
                SheetIssue(sheet_title, row_number, "missing course code, semester, or link")
            )
            continue
        rows.append(
            SyllabusIndexRow(
                course_code=course_code,
                instructor=instructor,
                semester=semester,
                school=current_school,
                syllabus_url=link,
                sheet_title=sheet_title,
                sheet_gid=sheet_gid,
                sheet_row=row_number,
            )
        )
    return rows, issues


def grid_range(sheet_title: str) -> str:
    return f"'{sheet_title.replace(chr(39), chr(39) * 2)}'!A:E"
