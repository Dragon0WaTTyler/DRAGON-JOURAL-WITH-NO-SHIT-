from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from reportlab.pdfgen.canvas import Canvas

from dragon.structured_extraction import DocumentExtractionError, extract_structured_document


def _zip(entries: dict[str, str]) -> bytes:
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return payload.getvalue()


def test_pdf_extraction_preserves_pages_metadata_and_nonverification() -> None:
    payload = BytesIO()
    canvas = Canvas(payload)
    canvas.setTitle("Official report")
    canvas.setAuthor("Public institution")
    canvas.drawString(72, 760, "First page with a substantive official result for structured extraction.")
    canvas.showPage()
    canvas.drawString(72, 760, "Second page with methods, limitations, and a source URL https://example.org/data")
    canvas.save()
    value = extract_structured_document(
        payload.getvalue(), content_type="application/pdf", source_url="https://example.org/report.pdf"
    )
    assert value["material_type"] == "PDF"
    assert value["title"] == "Official report"
    assert len(value["sections"]) == 2
    assert value["links"] == ["https://example.org/data"]
    assert value["verification_status"] == "EXTRACTED_NOT_VERIFIED"


def test_docx_extraction_preserves_paragraphs_and_table_rows() -> None:
    document = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
    <w:p><w:r><w:t>Official programme report with enough meaningful text for extraction.</w:t></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Year</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>
    <w:tr><w:tc><w:p><w:r><w:t>2026</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>12.5%</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
    </w:body></w:document>'''
    core = '''<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Programme report</dc:title><dc:creator>Ministry</dc:creator></cp:coreProperties>'''
    value = extract_structured_document(
        _zip({"word/document.xml": document, "docProps/core.xml": core}),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        source_url="https://example.org/report.docx",
    )
    assert value["title"] == "Programme report" and value["author"] == "Ministry"
    assert value["tables"][0][1] == ["2026", "12.5%"]


def test_xlsx_csv_and_json_extract_tables_deterministically() -> None:
    sheet = '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
    <row><c t="inlineStr"><is><t>السنة</t></is></c><c t="inlineStr"><is><t>القيمة</t></is></c></row>
    <row><c><v>2026</v></c><c><v>12.5</v></c></row></sheetData></worksheet>'''
    xlsx = extract_structured_document(
        _zip({"xl/worksheets/sheet1.xml": sheet}),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        source_url="https://example.org/data.xlsx",
    )
    csv_value = extract_structured_document(
        "السنة,القيمة\n2026,12.5\n".encode(),
        content_type="text/csv",
        source_url="https://example.org/data.csv",
    )
    json_value = extract_structured_document(
        b'[{"year":2026,"value":12.5}]',
        content_type="application/json",
        source_url="https://example.org/data.json",
    )
    assert xlsx["tables"][0][1] == ["2026", "12.5"]
    assert csv_value["tables"][0][1] == ["2026", "12.5"]
    assert json_value["tables"][0][0] == ["value", "year"]


def test_bad_pdf_empty_document_and_unsafe_office_archive_fail_closed() -> None:
    with pytest.raises(DocumentExtractionError) as bad_pdf:
        extract_structured_document(b"not a pdf", content_type="application/pdf", source_url="https://example.org/bad.pdf")
    assert bad_pdf.value.code == "DOCUMENT_PDF_INVALID"
    with pytest.raises(DocumentExtractionError) as empty:
        extract_structured_document(b"a,b\n", content_type="text/csv", source_url="https://example.org/empty.csv")
    assert empty.value.code == "DOCUMENT_EXTRACTION_EMPTY"
    unsafe = _zip({"../word/document.xml": "unsafe"})
    with pytest.raises(DocumentExtractionError) as traversal:
        extract_structured_document(
            unsafe,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            source_url="https://example.org/unsafe.docx",
        )
    assert traversal.value.code == "DOCUMENT_ARCHIVE_UNSAFE_PATH"
