# EPUB V1.1 root-cause record

Date: 2026-09-03

The prior EPUB was a valid ZIP, but every XHTML document began with the HTML-form doctype `<!doctype html>`. EPUB XHTML is XML; the strict XML parser rejects that lowercase declaration at line 1, column 0, which reproduces the reader's `StartTag: invalid element name` failure.

Affected members: `OEBPS/nav.xhtml` and `OEBPS/section-01.xhtml` through `OEBPS/section-13.xhtml`.

The V1.1 generator now emits UTF-8 XML/XHTML documents with an XML declaration and an XHTML namespace, builds a semantic nav document, creates a cover page and a Sources document, escapes all text before placing it in markup, and creates internal citation links plus external source URLs. Validation now strictly parses every XML/XHTML member, validates the OPF/spine/nav/local links/fragments, and rejects invalid UTF-8, malformed entities, duplicate IDs, missing semantic content, and unresolved TOC targets.
