"""Turn local PDF and DOCX syllabi into citation-bearing LangChain documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

PARSER_VERSION = "pymupdf-page-v1"
DOCX_PARSER_VERSION = "python-docx-block-v2"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CHUNK_SIZE = 2048


def _load_docx_blocks(path: Path) -> list[Document]:
    """Extract nonempty paragraphs and unique table rows in document order."""
    from docx import Document as WordDocument
    from docx.table import Table

    word = WordDocument(path)
    blocks: list[Document] = []
    heading: str | None = None
    section_index = 1

    def add_block(value: str) -> None:
        blocks.append(Document(
            page_content=value,
            metadata={"section": heading, "section_index": section_index,
                      "block_index": len(blocks) + 1},
        ))

    for block in word.iter_inner_content():
        if isinstance(block, Table):
            seen_cells = []
            for table_row in block.rows:
                values: list[str] = []
                for cell in table_row.cells:
                    identity = cell._tc
                    if any(identity is seen for seen in seen_cells):
                        continue
                    seen_cells.append(identity)
                    if value := cell.text.strip():
                        values.append(value)
                if values:
                    add_block(" | ".join(values))
        else:
            value = block.text.strip()
            if not value:
                continue
            if block.style.name.lower().startswith("heading"):
                if blocks:
                    section_index += 1
                heading = value
            add_block(value)
    return blocks


def _chunk_docx_blocks(
    blocks: list[Document], splitter: RecursiveCharacterTextSplitter
) -> list[Document]:
    """Pack whole source blocks; split only an oversized individual block."""
    chunks: list[Document] = []
    pending: list[Document] = []

    def flush() -> None:
        if not pending:
            return
        first, last = pending[0], pending[-1]
        chunks.append(Document(
            page_content="\n\n".join(block.page_content for block in pending),
            metadata={"section": first.metadata["section"],
                      "section_index": first.metadata["section_index"],
                      "block_start": first.metadata["block_index"],
                      "block_end": last.metadata["block_index"]},
        ))
        pending.clear()

    for block in blocks:
        if len(block.page_content) > CHUNK_SIZE:
            flush()
            for part_index, part in enumerate(splitter.split_text(block.page_content)):
                chunks.append(Document(
                    page_content=part,
                    metadata={"section": block.metadata["section"],
                              "section_index": block.metadata["section_index"],
                              "block_start": block.metadata["block_index"],
                              "block_end": block.metadata["block_index"],
                              "part_index": part_index},
                ))
            continue
        pending_length = sum(len(item.page_content) for item in pending) + max(len(pending) - 1, 0) * 2
        if pending and (pending_length + 2 + len(block.page_content) > CHUNK_SIZE
                        or pending[0].metadata["section_index"] != block.metadata["section_index"]):
            flush()
        pending.append(block)
    flush()
    return chunks


def load_syllabus_documents(
    manifest_path: Path,
    *,
    loader_factory: Callable[[Path], list[Document]] | None = None,
) -> list[Document]:
    """Load each downloaded record while retaining sheet and source locations."""

    splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        AutoTokenizer.from_pretrained('infgrad/Jasper-Token-Compression-600M'),
        chunk_size=CHUNK_SIZE,
        chunk_overlap=int(CHUNK_SIZE / 10),
    )
    documents: dict[str, Document] = {}
    current_records: dict[str, dict[str, object]] = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        if record.get("status") != "downloaded":
            continue
        current_records[str(record["source_url"])] = record
    for record in current_records.values():
        filename = str(record["local_path"])
        if Path(filename).name != filename:
            raise ValueError(f"Unsafe manifest path: {filename}")
        path = manifest_path.parent / filename
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != record["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {filename}")
        is_docx = record.get("content_type") == DOCX or path.suffix.lower() == ".docx"
        if is_docx:
            pages = _chunk_docx_blocks(_load_docx_blocks(path), splitter)
            parser_version = DOCX_PARSER_VERSION
        else:
            if loader_factory is None:
                from langchain_community.document_loaders import PyMuPDFLoader

                pages = PyMuPDFLoader(str(path), mode="page").load()
            else:
                pages = loader_factory(path)
            parser_version = PARSER_VERSION
        for page_index, page in enumerate(pages, start=1):
            location = (int(page.metadata["block_start"]) if is_docx
                        else int(page.metadata.get("page", page_index - 1)) + 1)
            chunks = [page.page_content] if is_docx else splitter.split_text(page.page_content)
            for chunk_index, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                if is_docx:
                    identity = (f"{record['source_url']}|{checksum}|{location}|"
                                f"{page.metadata['block_end']}|{page_index}|{parser_version}")
                else:
                    identity = (f"{record['source_url']}|{checksum}|{location}|"
                                f"{chunk_index}|{parser_version}")
                identifier = hashlib.sha256(identity.encode()).hexdigest()
                metadata = {
                    "document_id": identifier,
                    "source_url": record["syllabus_url"],
                    "index_url": record["source_url"],
                    "course_code": record["course_code"],
                    "instructor": record["instructor"],
                    "semester": record["semester"],
                    "school": record["school"],
                    "sheet_title": record["sheet_title"],
                    "sheet_gid": record["sheet_gid"],
                    "sheet_row": record["sheet_row"],
                    "sha256": checksum,
                    "retrieved_at": record["retrieved_at"],
                    "parser_version": parser_version,
                    "historical_source": True,
                }
                if is_docx:
                    metadata["section"] = page.metadata["section"]
                    metadata["section_index"] = page.metadata["section_index"]
                    metadata["block_start"] = page.metadata["block_start"]
                    metadata["block_end"] = page.metadata["block_end"]
                    if "part_index" in page.metadata:
                        metadata["part_index"] = page.metadata["part_index"]
                else:
                    metadata["page"] = location
                documents[identifier] = Document(page_content=chunk, metadata=metadata)
    return list(documents.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/processed/moe_syllabi_chunks.jsonl"))
    args = parser.parse_args()
    documents = load_syllabus_documents(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for document in documents:
            stream.write(json.dumps({"page_content": document.page_content,
                                     "metadata": document.metadata}, ensure_ascii=False) + "\n")
    temporary.replace(args.output)
    print(f"Wrote {len(documents)} chunks to {args.output}")


if __name__ == "__main__":
    main()
