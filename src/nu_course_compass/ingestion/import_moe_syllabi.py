"""Authenticated local import of the MOE syllabus index."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

import httpx

from nu_course_compass.ingestion.moe_sheet import (
    EXPECTED_GIDS,
    SPREADSHEET_ID,
    SyllabusIndexRow,
    grid_range,
    parse_sheet_grid,
)

SHEETS_API = "https://sheets.googleapis.com"
DRIVE_API = "https://www.googleapis.com"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_SLIDES = "application/vnd.google-apps.presentation"
GOOGLE_FOLDER = "application/vnd.google-apps.folder"
SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def google_credentials(client_secret: Path, token_path: Path) -> Any:
    """Use a user-authorized OAuth token; never reuse browser cookies."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not client_secret.is_file():
            raise FileNotFoundError(
                f"OAuth client JSON not found: {client_secret}. "
                "Create a Google Desktop OAuth client first."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        credentials = flow.run_local_server(port=0)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    return credentials


class GoogleReadClient:
    def __init__(self, credentials: Any, *, sleep: Callable[[float], None] = time.sleep) -> None:
        self.credentials = credentials
        self.http = httpx.Client(timeout=30)
        self.sleep = sleep

    def __enter__(self) -> GoogleReadClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.http.close()

    def get(self, path: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        from google.auth.transport.requests import Request

        if not self.credentials.valid:
            self.credentials.refresh(Request())
        if path.startswith("/v4/spreadsheets/"):
            base_url = SHEETS_API
        elif path.startswith("/drive/v3/files/"):
            base_url = DRIVE_API
        else:
            raise ValueError(f"Unsupported Google API path: {path}")
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.http.get(
                    f"{base_url}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {self.credentials.token}"},
                )
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                self.sleep(float(2**attempt))
                continue
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                retry_after = response.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdecimal() else 2**attempt
                self.sleep(float(min(delay, 60)))
                continue
            response.raise_for_status()
            return response
        raise AssertionError("Retry loop exhausted without a response")

    def sheet_rows(self) -> tuple[list[SyllabusIndexRow], list[dict[str, object]]]:
        metadata = self.get(
            f"/v4/spreadsheets/{SPREADSHEET_ID}",
            params={"fields": "sheets(properties(sheetId,title))"},
        ).json()
        rows: list[SyllabusIndexRow] = []
        issues: list[dict[str, object]] = []
        found: set[int] = set()
        for sheet in metadata.get("sheets", []):
            props = sheet["properties"]
            gid = int(props["sheetId"])
            if gid not in EXPECTED_GIDS:
                continue
            found.add(gid)
            title = str(props["title"])
            payload = self.get(
                f"/v4/spreadsheets/{SPREADSHEET_ID}",
                params={
                    "includeGridData": "true",
                    "ranges": grid_range(title),
                    "fields": "sheets(data(rowData(values(formattedValue,hyperlink,textFormatRuns))))",
                },
            ).json()
            grid = payload["sheets"][0]["data"][0]
            parsed, errors = parse_sheet_grid(
                sheet_title=title, sheet_gid=gid, grid=grid
            )
            rows.extend(parsed)
            issues.extend(
                {"sheet_title": error.sheet_title, "sheet_row": error.sheet_row,
                 "reason": error.reason}
                for error in errors
            )
        if found != EXPECTED_GIDS:
            raise ValueError(f"Missing expected sheet gids: {sorted(EXPECTED_GIDS - found)}")
        return rows, issues

    def file_metadata(self, file_id: str) -> dict[str, object]:
        return self.get(
            f"/drive/v3/files/{quote(file_id, safe='')}",
            params={"fields": "id,name,mimeType,modifiedTime,capabilities(canDownload)"},
        ).json()

    def download_pdf(self, file_id: str, mime_type: str) -> bytes:
        path = f"/drive/v3/files/{quote(file_id, safe='')}"
        params = {"alt": "media"}
        if mime_type in {GOOGLE_DOC, GOOGLE_SLIDES}:
            path += "/export"
            params = {"mimeType": PDF}
        content = self.get(path, params=params).content
        if not content.startswith(b"%PDF-"):
            raise ValueError("Google returned non-PDF content")
        return content

    def download_docx(self, file_id: str) -> bytes:
        content = self.get(
            f"/drive/v3/files/{quote(file_id, safe='')}", params={"alt": "media"}
        ).content
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("DOCX exceeds 20 MiB")
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Google returned non-DOCX content")
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError("DOCX uncompressed content exceeds 100 MiB")
        except zipfile.BadZipFile as error:
            raise ValueError("Google returned non-DOCX content") from error
        return content


def drive_file_id(url: str) -> tuple[str | None, str]:
    """Accept known Google file URLs only; never fetch arbitrary sheet links."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "drive.google.com", "docs.google.com"
    }:
        return None, "unsupported_url"
    parts = parsed.path.strip("/").split("/")
    if "folders" in parts:
        return None, "folder_link"
    if "d" not in parts:
        return None, "unsupported_url"
    index = parts.index("d")
    if index + 1 >= len(parts) or not parts[index + 1]:
        return None, "unsupported_url"
    file_id = parts[index + 1]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
        return None, "unsupported_url"
    return file_id, ""


def _read_manifest(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def import_rows(
    rows: list[SyllabusIndexRow], client: GoogleReadClient, output_dir: Path
) -> list[dict[str, object]]:
    """Append outcomes once; immutable source snapshots are named by content hash."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "manifest.jsonl"
    previous = _read_manifest(manifest)
    results: list[dict[str, object]] = []
    for row in rows:
        base: dict[str, object] = row.to_dict()
        base["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        file_id, reason = drive_file_id(row.syllabus_url)
        if not file_id:
            result = base | {"status": "skipped", "reason": reason}
        else:
            try:
                metadata = client.file_metadata(file_id)
                mime = str(metadata.get("mimeType", ""))
                modified = str(metadata.get("modifiedTime", ""))
                base.update(file_id=file_id, source_mime_type=mime, modified_time=modified)
                if mime == GOOGLE_FOLDER:
                    result = base | {"status": "skipped", "reason": "folder_link"}
                elif not metadata.get("capabilities", {}).get("canDownload", False):
                    result = base | {"status": "skipped", "reason": "download_disabled"}
                elif mime not in {PDF, DOCX, GOOGLE_DOC, GOOGLE_SLIDES}:
                    result = base | {"status": "skipped", "reason": "unsupported_mime"}
                else:
                    prior = next(
                        (item for item in reversed(previous)
                         if item.get("file_id") == file_id
                         and modified and item.get("modified_time") == modified
                         and item.get("status") == "downloaded"
                         and (output_dir / str(item.get("local_path", ""))).is_file()),
                        None,
                    )
                    if prior is not None:
                        if (prior.get("source_url") == row.source_url
                                and prior.get("syllabus_url") == row.syllabus_url):
                            results.append(prior | {"reused_file": True})
                            continue
                        result = base | {
                            "status": "downloaded", "content_type": prior["content_type"],
                            "sha256": prior["sha256"],
                            "local_path": prior["local_path"], "reused_file": True,
                        }
                    else:
                        content = (client.download_docx(file_id) if mime == DOCX
                                   else client.download_pdf(file_id, mime))
                        checksum = hashlib.sha256(content).hexdigest()
                        extension = "docx" if mime == DOCX else "pdf"
                        filename = f"{file_id}-{checksum[:16]}.{extension}"
                        destination = output_dir / filename
                        if not destination.exists():
                            destination.write_bytes(content)
                        result = base | {
                            "status": "downloaded", "content_type": DOCX if mime == DOCX else PDF,
                            "sha256": checksum, "local_path": filename,
                        }
            except (httpx.HTTPError, ValueError, KeyError) as error:
                reason = (
                    f"http_{error.response.status_code}"
                    if isinstance(error, httpx.HTTPStatusError)
                    else type(error).__name__
                )
                result = base | {"status": "failed", "reason": reason}
        results.append(result)
        if not any(
            old.get("source_url") == result.get("source_url")
            and old.get("syllabus_url") == result.get("syllabus_url")
            and old.get("status") == result.get("status")
            and old.get("sha256") == result.get("sha256")
            and old.get("reason") == result.get("reason")
            for old in previous
        ):
            with manifest.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
            previous.append(result)
    return results


def import_in_batches(
    rows: list[SyllabusIndexRow],
    client: GoogleReadClient,
    output_dir: Path,
    *,
    batch_size: int,
    batch_delay: float,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    """Persist each batch before a short cooldown; a rerun resumes via the manifest."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if batch_delay < 0:
        raise ValueError("batch_delay must not be negative")
    results: list[dict[str, object]] = []
    for start in range(0, len(rows), batch_size):
        if start:
            sleep(batch_delay)
        results.extend(import_rows(rows[start:start + batch_size], client, output_dir))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secret", type=Path, required=True)
    parser.add_argument("--token", type=Path, default=Path("data/raw/moe_syllabi/oauth_token.json"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/moe_syllabi"))
    parser.add_argument("--limit", type=int, help="Pilot row cap (default: 10; incompatible with --all-rows)")
    parser.add_argument("--row", action="append", default=[], help="Select gid:row; repeatable")
    parser.add_argument("--inventory", action="store_true", help="List index rows without downloading")
    parser.add_argument("--all-rows", action="store_true", help="Explicitly attempt all indexed rows")
    parser.add_argument("--batch-size", type=int, default=25,
                        help="Rows per checkpointed batch (default: 25)")
    parser.add_argument("--batch-delay", type=float, default=2.0,
                        help="Seconds to pause between batches (default: 2)")
    args = parser.parse_args()
    if args.limit is not None and (args.limit < 1 or args.limit > 100):
        parser.error("--limit must be between 1 and 100")
    if args.batch_size < 1 or args.batch_size > 100:
        parser.error("--batch-size must be between 1 and 100")
    if args.batch_delay < 0:
        parser.error("--batch-delay must not be negative")
    if args.all_rows and args.row:
        parser.error("Use --all-rows or --row, not both")
    if args.all_rows and args.limit is not None:
        parser.error("Use --all-rows or --limit, not both")
    if args.all_rows and args.inventory:
        parser.error("Use --all-rows or --inventory, not both")
    limit = args.limit if args.limit is not None else 10
    credentials = google_credentials(args.client_secret, args.token)
    with GoogleReadClient(credentials) as client:
        rows, issues = client.sheet_rows()
        if args.row:
            selected = set(args.row)
            rows = [row for row in rows if f"{row.sheet_gid}:{row.sheet_row}" in selected]
            missing = selected - {f"{row.sheet_gid}:{row.sheet_row}" for row in rows}
            if missing:
                parser.error(f"Rows not found: {sorted(missing)}")
            if len(rows) > limit:
                parser.error(f"Selected {len(rows)} rows but --limit is {limit}")
        if args.inventory:
            for row in rows[:limit]:
                print(json.dumps(row.to_dict(), ensure_ascii=False))
            print(json.dumps({"indexed_rows": len(rows), "sheet_issues": len(issues)}))
            return
        selected_rows = rows if args.all_rows else rows[:limit]
        results = import_in_batches(selected_rows, client, args.output,
                                    batch_size=args.batch_size,
                                    batch_delay=args.batch_delay)
    summary = {"indexed_rows": len(rows), "sheet_issues": len(issues),
               "attempted_rows": len(results),
               "downloaded": sum(row["status"] == "downloaded" and not row.get("reused_file")
                                 for row in results),
               "reused": sum(row["status"] == "downloaded" and bool(row.get("reused_file"))
                             for row in results),
               "skipped": sum(row["status"] == "skipped" for row in results),
               "failed": sum(row["status"] == "failed" for row in results)}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
