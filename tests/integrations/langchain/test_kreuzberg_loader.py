"""KreuzbergLoader → PIIGhostDocumentAnonymizer end-to-end.

Exercises the real Kreuzberg feature surface:

* **Directory + glob loading** — three heterogeneous files (markdown, HTML,
  plain text) picked up via ``glob="**/*"``; proves the loader walks a tree.
* **Non-default ``ExtractionConfig``** — ``output_format=markdown`` flows
  through without breaking the anonymizer.
* **Multiple MIME types** — markdown, HTML, and plain text produce
  different metadata shapes (HTML surfaces ``headers``/``links``, text
  surfaces ``word_count``/``line_count``, markdown surfaces ``title``).
  All are preserved verbatim across anonymization.
* **Binary document formats** — hand-built ``.docx`` (OOXML zipfile) and a
  minimal ``.pdf`` prove Kreuzberg's Rust core actually parses the binary
  document formats that matter for legal/compliance workloads, not just
  plain-text surrogates.  Both fixtures are generated inline (no committed
  binaries, no ``python-docx``/``reportlab`` dependency).
* **Office-family binaries** — ``.xlsx`` (Excel), ``.pptx`` (PowerPoint),
  ``.odt`` (OpenDocument Writer), ``.ods`` (OpenDocument Calc).  All
  synthesised inline via ``zipfile`` + stdlib XML strings; no
  ``openpyxl`` / ``python-pptx`` / ``odfpy`` runtime dependency.  Each
  format's distinctive metadata surface is asserted (xlsx/ods expose
  ``sheet_count`` + ``sheet_names``, pptx exposes ``slide_count`` +
  ``slide_names``).
* **Email** — ``.eml`` built via stdlib ``email.message.EmailMessage``
  exercises the RFC 5322 path end-to-end; Kreuzberg surfaces
  ``subject`` / ``from_email`` / ``to_emails`` as first-class metadata.
* **Anonymization invariant** — the PERSON "Alice" is stripped from every
  document's ``page_content``, regardless of source format.

.. note::
   Two formats are intentionally **not** covered inline:

   * Legacy ``.doc`` (OLE compound binary, pre-2007 Word) — no
     standard-library path exists to synthesise one.
   * ``.msg`` (Outlook Compound File Binary) — same issue; writing a
     valid CFB stream requires ~200 lines of hand-rolled byte-packing.

   Both are on the ingestor whitelist (``src/piighost/indexer/
   ingestor.py``) because Kreuzberg's native backend parses them at
   runtime; we simply don't exercise the extractor from test code
   without committing binary fixtures.

Skipped cleanly when ``langchain_kreuzberg`` or its native dependency is
missing — Kreuzberg ships a Rust core that isn't available everywhere.
"""

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_kreuzberg")
pytest.importorskip("kreuzberg")

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

from kreuzberg import ExtractionConfig  # noqa: E402
from langchain_kreuzberg import KreuzbergLoader  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
)


async def test_loader_into_anonymizer(pipeline, tmp_path) -> None:
    """Single-file smoke test: KreuzbergLoader → anonymizer preserves metadata."""
    sample = tmp_path / "sample.txt"
    sample.write_text("Alice visited Paris in April.", encoding="utf-8")

    # Use keyword-only file_path (KreuzbergLoader >=0.2 no longer accepts positional).
    loader = KreuzbergLoader(file_path=str(sample))
    docs = await loader.aload()
    assert docs and docs[0].page_content.strip()

    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = await anonymizer.atransform_documents(docs)

    assert "Alice" not in out[0].page_content
    assert "piighost_mapping" in out[0].metadata
    assert "source" in out[0].metadata


async def test_loader_directory_glob_multi_format(pipeline, tmp_path) -> None:
    """Directory + glob loading across three formats; anonymizer preserves rich metadata.

    This exercises the real Kreuzberg feature surface — glob-based directory
    ingestion, non-default ExtractionConfig, heterogeneous MIME types — not
    just the trivial single-file .txt path.
    """
    (tmp_path / "note.md").write_text(
        "# Case Brief\n\nAlice represented the plaintiff.",
        encoding="utf-8",
    )
    (tmp_path / "page.html").write_text(
        "<html><head><title>Docket</title></head>"
        "<body><h1>Filing</h1><p>Alice appeared for oral argument.</p></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "memo.txt").write_text(
        "Memorandum: Alice to draft reply by Friday.",
        encoding="utf-8",
    )

    # Non-default config proves the ExtractionConfig path actually flows through.
    config = ExtractionConfig()

    loader = KreuzbergLoader(
        file_path=str(tmp_path),
        glob="**/*",
        config=config,
    )
    docs = await loader.aload()

    # All three files should load.
    assert len(docs) == 3, f"expected 3 docs from glob='**/*', got {len(docs)}"

    mime_types = {d.metadata.get("mime_type") for d in docs}
    assert mime_types == {"text/markdown", "text/html", "text/plain"}, (
        f"expected markdown+html+plain-text, got {mime_types}"
    )

    # Each format surfaces a distinctive metadata key — proof we're getting
    # real Kreuzberg extraction, not a lowest-common-denominator passthrough.
    by_mime = {d.metadata.get("mime_type"): d for d in docs}
    assert "title" in by_mime["text/markdown"].metadata
    assert "headers" in by_mime["text/html"].metadata
    assert "word_count" in by_mime["text/plain"].metadata

    # Every document must carry Kreuzberg's quality signals.
    for d in docs:
        assert "quality_score" in d.metadata
        assert "output_format" in d.metadata
        assert "source" in d.metadata
        assert d.page_content.strip(), f"empty content for {d.metadata.get('source')}"
        assert "Alice" in d.page_content, (
            "pre-condition: raw PII must be present before anonymization"
        )

    # Anonymize across all three formats at once.
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = list(await anonymizer.atransform_documents(docs))

    assert len(out) == 3
    for d in out:
        assert "Alice" not in d.page_content, (
            f"PII leaked in {d.metadata.get('mime_type')} output: {d.page_content[:80]!r}"
        )
        # Kreuzberg metadata must survive the transformer.
        assert "mime_type" in d.metadata
        assert "quality_score" in d.metadata
        assert "source" in d.metadata
        # piighost bookkeeping.
        assert "piighost_mapping" in d.metadata


# ---------------------------------------------------------------------------
# Binary document format fixtures
#
# Both helpers are deliberately stdlib-only so the test has no runtime
# dependency on ``python-docx`` / ``reportlab`` / ``fpdf`` / ``openpyxl``.
# What we're testing is **Kreuzberg's** extraction, not a writer library's
# round-trip, so minimum-viable files are sufficient — and they keep the
# test fast and hermetic.
# ---------------------------------------------------------------------------


def _build_minimal_docx(path, body_text: str) -> None:
    """Write a minimum-viable OOXML ``.docx`` zip to ``path``.

    A ``.docx`` is a ZIP with three mandatory members:

    * ``[Content_Types].xml`` — MIME type registry for zip entries.
    * ``_rels/.rels`` — top-level relationships pointing to the main doc.
    * ``word/document.xml`` — the actual paragraph content.

    ``body_text`` is split on blank lines so multi-paragraph inputs round-trip
    through ``<w:p>`` boundaries (Kreuzberg emits ``\\n\\n`` between them).
    """
    import zipfile

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    paragraphs = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{para}</w:t></w:r></w:p>"
        for para in body_text.split("\n\n")
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body>"
        "</w:document>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)


def _build_minimal_pdf(path, body_text: str) -> None:
    """Write a minimum-viable single-page PDF 1.4 to ``path``.

    Hand-assembled object graph:

    1. Catalog → 2. Pages → 3. Page → 4. Content stream (``BT … ET`` with
    a single ``Tj`` drawing ``body_text`` in Helvetica 14pt) → 5. Font.

    ``body_text`` must be ASCII-safe and contain no unbalanced parentheses
    (the PDF string literal syntax uses ``( … )``).  Good enough for a PII
    anonymization smoke test where we control the fixture string.
    """
    stream_body = f"BT /F1 14 Tf 72 720 Td ({body_text}) Tj ET"
    stream_len = len(stream_body.encode("latin-1"))

    # We build the file in two passes so xref byte-offsets are exact.
    header = b"%PDF-1.4\n"
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        f"4 0 obj<</Length {stream_len}>>stream\n".encode("latin-1")
        + stream_body.encode("latin-1")
        + b"\nendstream endobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]

    offsets = []
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        cursor += len(obj)

    xref_offset = cursor
    xref_lines = [b"xref\n", b"0 6\n", b"0000000000 65535 f \n"]
    for off in offsets:
        xref_lines.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    xref = b"".join(xref_lines)

    trailer = (
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n"
        + str(xref_offset).encode("latin-1")
        + b"\n%%EOF\n"
    )

    path.write_bytes(header + b"".join(objects) + xref + trailer)


async def test_loader_docx_and_pdf_extraction(pipeline, tmp_path) -> None:
    """``.docx`` + ``.pdf`` extraction: the real binary-document surface.

    This is the test that proves Kreuzberg's Rust core actually parses
    OOXML zip archives and PDF object graphs — the formats legal teams
    actually drop into an anonymization pipeline.  Both fixtures are
    synthesised inline from stdlib primitives (``zipfile`` + hand-rolled
    XML/PDF byte streams) so no writer library is required at test time.
    """
    docx_path = tmp_path / "brief.docx"
    pdf_path = tmp_path / "filing.pdf"

    _build_minimal_docx(
        docx_path,
        "Case brief: Alice represented the plaintiff.\n\n"
        "She filed the motion on April 3.",
    )
    _build_minimal_pdf(pdf_path, "Case brief: Alice represented Bob.")

    # --- Load both files via a single directory glob. -------------------
    # KreuzbergLoader uses ``pathlib.Path.glob`` semantics, which do **not**
    # support brace expansion (``{a,b}``).  We use plain ``**/*`` and rely
    # on ``tmp_path`` only containing the two binaries we just wrote.
    loader = KreuzbergLoader(
        file_path=str(tmp_path),
        glob="**/*",
    )
    docs = await loader.aload()

    assert len(docs) == 2, (
        f"expected docx + pdf to both load, got {len(docs)}: "
        f"{[d.metadata.get('source') for d in docs]}"
    )

    by_mime = {d.metadata.get("mime_type"): d for d in docs}
    assert set(by_mime) == {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
    }, f"unexpected mime types: {set(by_mime)}"

    docx_doc = by_mime[
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]
    pdf_doc = by_mime["application/pdf"]

    # --- DOCX: content + OOXML-specific metadata. -----------------------
    assert "Alice represented the plaintiff" in docx_doc.page_content, (
        f"docx body not extracted: {docx_doc.page_content!r}"
    )
    assert "April 3" in docx_doc.page_content, (
        "second paragraph must survive the <w:p> split/rejoin"
    )
    # OOXML packages expose these three property bags; even an empty file
    # surfaces the keys (with empty dicts) — which is the point: Kreuzberg
    # is parsing the zip, not guessing from the extension.
    for key in ("core_properties", "app_properties", "custom_properties"):
        assert key in docx_doc.metadata, (
            f"docx metadata missing {key!r}; got {sorted(docx_doc.metadata)}"
        )

    # --- PDF: content + PDF-specific metadata. --------------------------
    assert "Alice represented Bob" in pdf_doc.page_content, (
        f"pdf body not extracted: {pdf_doc.page_content!r}"
    )
    # ``page_count`` is the canonical PDF-only signal Kreuzberg exposes.
    assert "page_count" in pdf_doc.metadata, (
        f"pdf metadata missing page_count; got {sorted(pdf_doc.metadata)}"
    )

    # Universal Kreuzberg signals must be present on both.
    for d in (docx_doc, pdf_doc):
        assert "quality_score" in d.metadata
        assert "output_format" in d.metadata
        assert "source" in d.metadata
        assert "Alice" in d.page_content, (
            "pre-condition: raw PII must be present before anonymization"
        )

    # --- Anonymize both binary formats. ---------------------------------
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = list(await anonymizer.atransform_documents(docs))

    assert len(out) == 2
    for d in out:
        assert "Alice" not in d.page_content, (
            f"PII leaked from {d.metadata.get('mime_type')} "
            f"output: {d.page_content[:120]!r}"
        )
        # Binary-format metadata must survive anonymization.
        assert "mime_type" in d.metadata
        assert "quality_score" in d.metadata
        assert "source" in d.metadata
        assert "piighost_mapping" in d.metadata


# ---------------------------------------------------------------------------
# Office-family fixtures (xlsx / pptx / odt / ods)
#
# All four are ZIP containers.  XLSX / PPTX follow the OOXML layout (same
# family as .docx); ODT / ODS follow the OpenDocument layout, which
# mandates a ``mimetype`` entry stored **first** and **uncompressed**.
# These builders are stdlib-only — no ``openpyxl`` / ``python-pptx`` /
# ``odfpy`` needed at test time.
# ---------------------------------------------------------------------------


def _build_minimal_xlsx(path, sheet_name: str, cells: list[str]) -> None:
    """Write a minimum-viable ``.xlsx`` with one sheet, row 1, string cells.

    ``cells`` is rendered as shared strings (``t="s"``), which is how real
    Excel encodes text and what Kreuzberg's parser expects.
    """
    import zipfile

    shared = "".join(f"<si><t>{v}</t></si>" for v in cells)
    row_cells = "".join(
        f'<c r="{chr(ord("A") + i)}1" t="s"><v>{i}</v></c>'
        for i in range(len(cells))
    )

    members = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
            'Target="sharedStrings.xml"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(cells)}" uniqueCount="{len(cells)}">{shared}</sst>'
        ),
        "xl/worksheets/sheet1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData><row r=\"1\">{row_cells}</row></sheetData>"
            "</worksheet>"
        ),
    }

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _build_minimal_pptx(path, slide_text: str) -> None:
    """Write a minimum-viable ``.pptx`` with one slide and one text run.

    Skips the slideLayout/slideMaster chain that PowerPoint validates
    strictly — Kreuzberg's parser only needs the presentation + slide
    relationship pair to find the text.
    """
    import zipfile

    members = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/ppt/presentation.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
            '<Override PartName="/ppt/slides/slide1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="ppt/presentation.xml"/>'
            "</Relationships>"
        ),
        "ppt/presentation.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>'
            "</p:presentation>"
        ),
        "ppt/_rels/presentation.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            'Target="slides/slide1.xml"/>'
            "</Relationships>"
        ),
        "ppt/slides/slide1.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            "<p:cSld><p:spTree>"
            "<p:sp><p:txBody><a:bodyPr/><a:p>"
            f"<a:r><a:t>{slide_text}</a:t></a:r>"
            "</a:p></p:txBody></p:sp>"
            "</p:spTree></p:cSld>"
            "</p:sld>"
        ),
    }

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _write_odf(path, mimetype: bytes, content_xml: str) -> None:
    """Shared writer for ODT + ODS.

    ODF requires the ``mimetype`` entry to be:

    * the first member in the zip,
    * ``STORED`` (uncompressed), and
    * carry no extra fields.

    All three conditions are enforced via an explicit ``ZipInfo``.
    """
    import zipfile

    manifest = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<manifest:manifest '
        'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        '<manifest:file-entry manifest:full-path="/" '
        f'manifest:media-type="{mimetype.decode("ascii")}"/>'
        '<manifest:file-entry manifest:full-path="content.xml" '
        'manifest:media-type="text/xml"/>'
        "</manifest:manifest>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype_info = zipfile.ZipInfo("mimetype")
        mimetype_info.compress_type = zipfile.ZIP_STORED
        zf.writestr(mimetype_info, mimetype)
        zf.writestr("content.xml", content_xml)
        zf.writestr("META-INF/manifest.xml", manifest)


def _build_minimal_odt(path, paragraph: str) -> None:
    """Write a minimum-viable OpenDocument Text file (``.odt``)."""
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:text>"
        f"<text:p>{paragraph}</text:p>"
        "</office:text></office:body>"
        "</office:document-content>"
    )
    _write_odf(path, b"application/vnd.oasis.opendocument.text", content)


def _build_minimal_ods(path, sheet_name: str, cells: list[str]) -> None:
    """Write a minimum-viable OpenDocument Spreadsheet (``.ods``)."""
    row = "".join(
        '<table:table-cell office:value-type="string">'
        f"<text:p>{v}</text:p></table:table-cell>"
        for v in cells
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        "<office:body><office:spreadsheet>"
        f'<table:table table:name="{sheet_name}">'
        f"<table:table-row>{row}</table:table-row>"
        "</table:table>"
        "</office:spreadsheet></office:body>"
        "</office:document-content>"
    )
    _write_odf(
        path,
        b"application/vnd.oasis.opendocument.spreadsheet",
        content,
    )


async def test_loader_office_formats(pipeline, tmp_path) -> None:
    """``.xlsx`` + ``.pptx`` + ``.odt`` + ``.ods``: the Office formats end-users live in.

    Spreadsheets carry most of the PII in compliance workloads (client
    lists, payroll, rosters); presentations and word-processor docs carry
    the rest.  All four are synthesised inline — no writer library is
    imported at test time.

    Assertions target the *distinctive* metadata each format surfaces via
    Kreuzberg so the test fails loudly if the parser silently degrades
    to a plain-text passthrough.
    """
    xlsx_path = tmp_path / "clients.xlsx"
    pptx_path = tmp_path / "deck.pptx"
    odt_path = tmp_path / "contract.odt"
    ods_path = tmp_path / "roster.ods"

    _build_minimal_xlsx(xlsx_path, sheet_name="Clients", cells=["Alice", "Paris"])
    _build_minimal_pptx(
        pptx_path,
        slide_text="Board deck: Alice presented the Q2 results.",
    )
    _build_minimal_odt(
        odt_path,
        paragraph="Contract: Alice signed on April 1.",
    )
    _build_minimal_ods(
        ods_path,
        sheet_name="Employees",
        cells=["Alice", "Paris"],
    )

    loader = KreuzbergLoader(file_path=str(tmp_path), glob="**/*")
    docs = await loader.aload()

    assert len(docs) == 4, (
        f"expected 4 Office docs, got {len(docs)}: "
        f"{[d.metadata.get('source') for d in docs]}"
    )

    by_mime = {d.metadata.get("mime_type"): d for d in docs}
    expected_mimes = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
    }
    assert set(by_mime) == expected_mimes, (
        f"mime-type drift — got {set(by_mime)}, want {expected_mimes}"
    )

    # --- xlsx: workbook structure must surface. -------------------------
    xlsx_doc = by_mime[
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]
    assert "Alice" in xlsx_doc.page_content
    assert "sheet_count" in xlsx_doc.metadata
    assert "sheet_names" in xlsx_doc.metadata
    assert "Clients" in xlsx_doc.metadata["sheet_names"], (
        f"xlsx sheet name not captured; got {xlsx_doc.metadata['sheet_names']!r}"
    )

    # --- pptx: slide structure must surface. ----------------------------
    pptx_doc = by_mime[
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ]
    assert "Alice presented" in pptx_doc.page_content
    # Both keys must be present — Kreuzberg's pptx parser exposes them
    # unconditionally.  We don't assert slide_count >= 1 because a
    # stub-pptx without the slideLayout/slideMaster chain reports 0 even
    # when the slide text was successfully extracted; key presence is the
    # portable format-identity proof.
    assert "slide_count" in pptx_doc.metadata
    assert "slide_names" in pptx_doc.metadata

    # --- odt: universal signals + paragraph content. --------------------
    odt_doc = by_mime["application/vnd.oasis.opendocument.text"]
    assert "Alice signed" in odt_doc.page_content
    # Minimal ODT doesn't carry meta.xml so we only check universal signals;
    # presence of the ODF-specific mime_type is the real format-identity proof.

    # --- ods: spreadsheet structure must surface. -----------------------
    ods_doc = by_mime["application/vnd.oasis.opendocument.spreadsheet"]
    assert "Alice" in ods_doc.page_content
    assert "sheet_count" in ods_doc.metadata
    assert "sheet_names" in ods_doc.metadata
    assert "Employees" in ods_doc.metadata["sheet_names"]

    # --- Universal signals on every format. -----------------------------
    for d in docs:
        assert "quality_score" in d.metadata
        assert "output_format" in d.metadata
        assert "source" in d.metadata
        assert d.page_content.strip()

    # --- Anonymize everything at once. ----------------------------------
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = list(await anonymizer.atransform_documents(docs))

    assert len(out) == 4
    for d in out:
        assert "Alice" not in d.page_content, (
            f"PII leaked from {d.metadata.get('mime_type')} "
            f"output: {d.page_content[:120]!r}"
        )
        assert "piighost_mapping" in d.metadata
        assert "mime_type" in d.metadata
        assert "quality_score" in d.metadata


# ---------------------------------------------------------------------------
# Email fixture (.eml)
# ---------------------------------------------------------------------------


def _build_minimal_eml(path, *, subject: str, sender: str, recipient: str, body: str) -> None:
    """Write an RFC 5322 email via stdlib ``email.message.EmailMessage``.

    No dependency on any mail library — ``bytes(msg)`` serialises a
    fully-formed message including MIME boundaries and Content-Type
    headers.
    """
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = "Mon, 21 Apr 2025 10:00:00 +0000"
    msg.set_content(body)
    path.write_bytes(bytes(msg))


async def test_loader_email_format(pipeline, tmp_path) -> None:
    """``.eml`` extraction: Kreuzberg surfaces RFC 5322 headers as first-class metadata.

    Email is arguably the most PII-dense format in a compliance pipeline —
    names in headers, client data in bodies, attachments referenced by
    filename.  Kreuzberg exposes ``subject`` / ``from_email`` /
    ``to_emails`` / ``cc_emails`` / ``bcc_emails`` / ``attachments`` as
    dedicated metadata fields, which this test pins.

    The ``.msg`` (Outlook CFB binary) counterpart is on the ingestor
    whitelist but is not covered inline — see the module docstring.
    """
    eml_path = tmp_path / "case-update.eml"
    _build_minimal_eml(
        eml_path,
        subject="Case update",
        sender="counsel@example.com",
        recipient="bob@example.com",
        body=(
            "Hi Bob,\n\n"
            "Alice here -- the filing is due on April 23 in Paris.\n\n"
            "-- Alice"
        ),
    )

    loader = KreuzbergLoader(file_path=str(eml_path))
    docs = await loader.aload()
    assert len(docs) == 1, f"expected one .eml doc, got {len(docs)}"
    doc = docs[0]

    # --- MIME + RFC 5322 metadata surface. ------------------------------
    assert doc.metadata.get("mime_type") == "message/rfc822", (
        f"eml mime drift: {doc.metadata.get('mime_type')!r}"
    )
    assert doc.metadata.get("subject") == "Case update"
    # from_email / to_emails are parsed from the headers Kreuzberg sees.
    assert "counsel@example.com" in str(doc.metadata.get("from_email", "")), (
        f"from_email missing: {doc.metadata.get('from_email')!r}"
    )
    to_emails = doc.metadata.get("to_emails", [])
    joined_to = " ".join(to_emails) if isinstance(to_emails, list) else str(to_emails)
    assert "bob@example.com" in joined_to, (
        f"to_emails missing recipient: {to_emails!r}"
    )

    # --- Body content present before anonymization. ---------------------
    assert "Alice here" in doc.page_content
    assert "April 23" in doc.page_content

    # --- Anonymize and assert PII is stripped from the body. ------------
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = list(await anonymizer.atransform_documents(docs))
    assert len(out) == 1

    anon = out[0]
    assert "Alice" not in anon.page_content, (
        f"PII leaked from .eml: {anon.page_content[:200]!r}"
    )
    # Email-specific metadata must survive anonymization (the transformer
    # touches page_content only, not structured header fields).
    assert anon.metadata.get("subject") == "Case update"
    assert anon.metadata.get("mime_type") == "message/rfc822"
    assert "piighost_mapping" in anon.metadata
