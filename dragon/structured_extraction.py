"""Bounded local extraction for structured documents and table-oriented sources."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
import csv
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


class DocumentExtractionError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


MATERIAL_TYPES = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "text/csv": "CSV",
    "application/csv": "CSV",
    "application/json": "JSON",
    "text/json": "JSON",
}

MAX_ZIP_MEMBERS = 2_000
MAX_UNCOMPRESSED_BYTES = 25_000_000


def _safe_zip(payload: bytes) -> ZipFile:
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise DocumentExtractionError("DOCUMENT_ARCHIVE_INVALID", str(exc)) from exc
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        archive.close()
        raise DocumentExtractionError("DOCUMENT_ARCHIVE_LIMIT_EXCEEDED", "too many members")
    if sum(item.file_size for item in members) > MAX_UNCOMPRESSED_BYTES:
        archive.close()
        raise DocumentExtractionError("DOCUMENT_ARCHIVE_LIMIT_EXCEEDED", "expanded bytes exceed limit")
    for item in members:
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts:
            archive.close()
            raise DocumentExtractionError("DOCUMENT_ARCHIVE_UNSAFE_PATH", item.filename)
    return archive


def _pdf(payload: bytes) -> tuple[str | None, str | None, list[str], list[list[list[str]]]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(payload), strict=True)
        if reader.is_encrypted:
            raise DocumentExtractionError("DOCUMENT_PDF_ENCRYPTED", "encrypted PDF")
        sections = [(page.extract_text() or "").strip() for page in reader.pages]
        metadata = reader.metadata or {}
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError("DOCUMENT_PDF_INVALID", str(exc)) from exc
    return metadata.get("/Title"), metadata.get("/Author"), sections, []


def _docx(payload: bytes) -> tuple[str | None, str | None, list[str], list[list[list[str]]]]:
    with _safe_zip(payload) as archive:
        try:
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        except (KeyError, ElementTree.ParseError) as exc:
            raise DocumentExtractionError("DOCUMENT_DOCX_INVALID", str(exc)) from exc
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        sections = []
        for paragraph in document.iter(namespace + "p"):
            value = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
            if value:
                sections.append(value)
        tables = []
        for table in document.iter(namespace + "tbl"):
            rows = []
            for row in table.findall(".//" + namespace + "tr"):
                cells = []
                for cell in row.findall("./" + namespace + "tc"):
                    cells.append(" ".join(
                        (node.text or "").strip()
                        for node in cell.iter(namespace + "t")
                        if (node.text or "").strip()
                    ))
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        title = author = None
        try:
            core = ElementTree.fromstring(archive.read("docProps/core.xml"))
            title = next((node.text for node in core.iter() if node.tag.endswith("}title")), None)
            author = next((node.text for node in core.iter() if node.tag.endswith("}creator")), None)
        except (KeyError, ElementTree.ParseError):
            pass
    return title, author, sections, tables


def _xlsx_cell(cell: ElementTree.Element, shared: list[str]) -> str:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    value = cell.find(namespace + "v")
    if cell.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(namespace + "t"))
    raw = value.text if value is not None and value.text is not None else ""
    if cell.get("t") == "s" and raw.isdigit() and int(raw) < len(shared):
        return shared[int(raw)]
    return raw


def _xlsx(payload: bytes) -> tuple[str | None, str | None, list[str], list[list[list[str]]]]:
    with _safe_zip(payload) as archive:
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared = []
        try:
            strings = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(namespace + "t")) for item in strings]
        except KeyError:
            pass
        except ElementTree.ParseError as exc:
            raise DocumentExtractionError("DOCUMENT_XLSX_INVALID", str(exc)) from exc
        tables = []
        sheet_names = sorted(
            item.filename for item in archive.infolist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", item.filename)
        )
        if not sheet_names:
            raise DocumentExtractionError("DOCUMENT_XLSX_INVALID", "no worksheets")
        for sheet_name in sheet_names:
            try:
                sheet = ElementTree.fromstring(archive.read(sheet_name))
            except ElementTree.ParseError as exc:
                raise DocumentExtractionError("DOCUMENT_XLSX_INVALID", str(exc)) from exc
            rows = [
                [_xlsx_cell(cell, shared) for cell in row.findall(namespace + "c")]
                for row in sheet.iter(namespace + "row")
            ]
            tables.append([row for row in rows if row])
    sections = [" | ".join(row) for table in tables for row in table]
    return None, None, sections, tables


def _csv(payload: bytes) -> tuple[str | None, str | None, list[str], list[list[list[str]]]]:
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise DocumentExtractionError("DOCUMENT_TEXT_ENCODING_INVALID", str(exc)) from exc
    rows = [row for row in csv.reader(StringIO(text)) if row]
    return None, None, [" | ".join(row) for row in rows], [rows] if rows else []


def _json(payload: bytes) -> tuple[str | None, str | None, list[str], list[list[list[str]]]]:
    try:
        value = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DocumentExtractionError("DOCUMENT_JSON_INVALID", str(exc)) from exc
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    tables = []
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        headers = sorted({key for item in value for key in item})
        tables.append([headers, *[[str(item.get(key, "")) for key in headers] for item in value]])
    title = value.get("title") if isinstance(value, dict) and isinstance(value.get("title"), str) else None
    return title, None, [canonical], tables


def extract_structured_document(
    payload: bytes,
    *,
    content_type: str,
    source_url: str,
    retrieved_at: str | None = None,
) -> dict:
    material_type = MATERIAL_TYPES.get(content_type)
    if not material_type:
        raise DocumentExtractionError("DOCUMENT_TYPE_UNSUPPORTED", content_type)
    parser = {"PDF": _pdf, "DOCX": _docx, "XLSX": _xlsx, "CSV": _csv, "JSON": _json}[material_type]
    title, author, sections, tables = parser(payload)
    sections = [" ".join(value.split()) for value in sections if value and value.strip()]
    text = "\n\n".join(sections).strip()
    if len(text) < 20:
        raise DocumentExtractionError("DOCUMENT_EXTRACTION_EMPTY", source_url)
    links = sorted(set(re.findall(r"https://[^\s<>()\]\[{}]+", text)))
    structured_fields = {}
    # Preserve only explicitly labelled portal/document fields.  This is
    # metadata for downstream event extraction, never an inferred value.
    if material_type == "JSON":
        try:
            value = json.loads(payload.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict):
            for key in ("notice_number", "reference", "publication_date", "deadline", "issuer", "status", "category", "description", "effective_start", "effective_end"):
                if key in value and value[key] not in (None, "", []):
                    structured_fields[key] = value[key]
    elif tables and tables[0]:
        headers = [str(item).strip().casefold() for item in tables[0][0]]
        if headers and any(item in headers for item in ("notice_number", "reference", "deadline", "issuer", "status", "category")):
            row = tables[0][1] if len(tables[0]) > 1 else []
            structured_fields = {
                headers[index]: row[index] for index in range(min(len(headers), len(row)))
                if headers[index] in {"notice_number", "reference", "publication_date", "deadline", "issuer", "status", "category", "description"} and row[index] not in (None, "")
            }
    return {
        "canonical_url": source_url,
        "discovered_url": source_url,
        "title": title or PurePosixPath(urlsplit(source_url).path).name or None,
        "author": author,
        "publisher": urlsplit(source_url).hostname,
        "published_at": None,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "fetch_status": "FETCHED",
        "http_status": 200,
        "content_type": content_type,
        "material_type": material_type,
        "extraction_method": f"dragon-structured-{material_type.casefold()}",
        "extraction_quality": "HIGH" if len(text) >= 1_000 else "MEDIUM",
        "quality_score": min(1.0, round(len(text) / 1_000, 3)),
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "language": None,
        "text": text,
        "sections": sections,
        "tables": tables,
        "structured_fields": structured_fields,
        "links": links,
        "verification_status": "EXTRACTED_NOT_VERIFIED",
    }
