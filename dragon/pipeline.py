"""Concrete DRAGON V5 stages shared by production and synthetic acceptance runs."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

from dragon.builtin_stages import preflight_stage
from dragon.archive import ArchiveError, DisabledGitArchiveProvider
from dragon.language import decode_utf8, validate_arabic_text, validate_html_rtl
from dragon.providers import EditorialProvider, ProviderError, SECTION_HEADINGS
from dragon.publication import (
    artifact_manifest,
    build_epub,
    build_html,
    cover_svg,
    render_pdf,
    validate_epub,
    validate_pdf,
)
from dragon.stages import StageContext, StageDefinition, StageFailure, StageResult
from dragon.state import atomic_write_json
from dragon.whatsapp import DisabledWhatsAppProvider, WhatsAppError


def _load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8", newline="\n")
    return path


def _json_stage(name: str, prerequisites: tuple[str, ...], runner):
    return StageDefinition(name=name, prerequisites=prerequisites, runner=runner)


def synthetic_preflight_stage() -> StageDefinition:
    def run(context: StageContext) -> StageResult:
        report = {
            "status": "PASS",
            "mode": "synthetic",
            "edition_date": context.edition_date,
            "warning": "اختبار محلي صريح؛ فحوص الشبكة ومزود التحرير غير مطبقة",
            "blocking_failures": [],
            "checks": [
                {"name": "synthetic_mode_explicit", "status": "PASS"},
                {"name": "production_preflight", "status": "NOT_APPLICABLE"},
            ],
        }
        path = context.run_dir / "preflight.json"
        atomic_write_json(path, report)
        return StageResult(outputs=(path,))

    return StageDefinition("preflight", (), run)


def build_stage_definitions(provider: EditorialProvider, *, synthetic: bool = False, archive_provider=None, whatsapp_provider=None) -> list[StageDefinition]:
    archive_provider = archive_provider or DisabledGitArchiveProvider()
    whatsapp_provider = whatsapp_provider or DisabledWhatsAppProvider()
    def research(context: StageContext) -> StageResult:
        try:
            packet = provider.research(context.edition_date)
        except ProviderError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        packet["provider_mode"] = provider.mode
        path = context.run_dir / "research" / "research-packet.json"
        atomic_write_json(path, packet)
        return StageResult((path,))

    def articles(context: StageContext) -> StageResult:
        packet = _load(context.run_dir / "research" / "research-packet.json")
        try:
            values = provider.articles(packet)
        except ProviderError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        path = context.run_dir / "articles" / "articles.json"
        atomic_write_json(path, {"mode": provider.mode, "articles": values})
        return StageResult((path,))

    def chief_editor(context: StageContext) -> StageResult:
        values = _load(context.run_dir / "articles" / "articles.json")
        articles_value = values["articles"]
        decisions = {item["section_id"]: item for item in articles_value}
        inventory = [
            {
                "section_id": section_id,
                "heading": heading,
                "status": decisions[section_id]["status"],
                "skip_reason": decisions[section_id].get("skip_reason"),
            }
            for section_id, heading in SECTION_HEADINGS
        ]
        plan = {
            "schema_version": 5,
            "mode": provider.mode,
            "edition_date": context.edition_date,
            "language": "ar",
            "direction": "rtl",
            "section_inventory": inventory,
            "article_ids": [item["id"] for item in articles_value if item["status"] == "ACTIVE"],
        }
        plan_path = context.edition_dir / "edition-plan.json"
        atomic_write_json(plan_path, plan)
        packet = _load(context.run_dir / "research" / "research-packet.json")
        sources_path = context.edition_dir / "sources.json"
        atomic_write_json(sources_path, {"sources": packet["sources"]})
        lines = [f"# DRAGON — {context.edition_date}", ""]
        if synthetic:
            lines.extend(["> نسخة اختبار اصطناعية غير مخصصة للنشر.", ""])
        sources_by_id = {source["id"]: source["url"] for source in packet["sources"]}
        for item in articles_value:
            if item["status"] == "SKIPPED":
                lines.extend([f"## {item['section']}", "", f"لم ينشر هذا القسم: {item['skip_reason']}", ""])
                continue
            item["source_urls"] = [sources_by_id[source_id] for source_id in item["source_ids"]]
            lines.extend([f"## {item['section']}: {item['headline']}", "", item["standfirst"], "", f"**{item['byline']}**", ""])
            lines.extend([paragraph + "\n" for paragraph in item["body"]])
            lines.extend([f"المصدر: {sources_by_id[source_id]}" for source_id in item["source_ids"]])
            lines.append("")
        markdown = _write_text(context.edition_dir / "edition.md", "\n".join(lines))
        canonical_articles = context.edition_dir / "articles.json"
        atomic_write_json(canonical_articles, values)
        return StageResult((plan_path, sources_path, markdown, canonical_articles))

    def factcheck(context: StageContext) -> StageResult:
        articles_value = _load(context.edition_dir / "articles.json")["articles"]
        active_articles = [item for item in articles_value if item["status"] == "ACTIVE"]
        issues = [item["id"] for item in active_articles if not item.get("source_ids")]
        report = {
            "status": "PASS" if not issues else "FAIL",
            "mode": provider.mode,
            "method": "synthetic_non_factual_fixture" if synthetic else "provider_source_linkage_only",
            "checked_articles": len(active_articles),
            "missing_source_articles": issues,
            "warning": "الاختبار الاصطناعي لا يثبت صحة أخبار حقيقية" if synthetic else None,
        }
        path = context.run_dir / "factcheck" / "report.json"
        atomic_write_json(path, report)
        if issues:
            raise StageFailure("FACTCHECK_FAILED", "articles without sources", outputs=(path,))
        return StageResult((path,))

    def arabic_qa(context: StageContext) -> StageResult:
        articles_value = _load(context.edition_dir / "articles.json")["articles"]
        text = "\n".join(
            " ".join([item["section"], item["headline"], item["standfirst"], *item["body"]])
            for item in articles_value if item["status"] == "ACTIVE"
        )
        qa = validate_arabic_text(text, minimum_arabic_letters=500, allowed_latin_terms=("DRAGON",))
        path = context.run_dir / "qa" / "arabic-language.json"
        atomic_write_json(path, qa.to_dict())
        if qa.status != "PASS":
            raise StageFailure("ARABIC_LANGUAGE_QA_FAILED", "; ".join(qa.issues), outputs=(path,))
        return StageResult((path,))

    def cover(context: StageContext) -> StageResult:
        path = _write_text(context.edition_dir / "assets" / "cover.svg", cover_svg(context.edition_date, mode=provider.mode))
        try:
            root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
        except ElementTree.ParseError as exc:
            raise StageFailure("COVER_SVG_INVALID", str(exc), outputs=(path,)) from exc
        if not root.tag.endswith("svg"):
            raise StageFailure("COVER_SVG_INVALID", "root is not svg", outputs=(path,))
        brief = context.edition_dir / "cover-brief.json"
        atomic_write_json(brief, {"mode": provider.mode, "canonical": "assets/cover.svg", "accepted": True, "warning": "غلاف اختبار اصطناعي" if synthetic else None})
        return StageResult((path, brief))

    def publication_source(context: StageContext) -> StageResult:
        articles_value = [item for item in _load(context.edition_dir / "articles.json")["articles"] if item["status"] == "ACTIVE"]
        path = build_html(context.edition_dir, context.edition_date, articles_value, mode=provider.mode)
        document = decode_utf8(path.read_bytes())
        issues = validate_html_rtl(document)
        if issues:
            raise StageFailure("PUBLICATION_SOURCE_INVALID", "; ".join(issues), outputs=(path,))
        return StageResult((path, context.edition_dir / "print-v5.css"))

    def pdf(context: StageContext) -> StageResult:
        path = render_pdf(context.edition_dir / "edition.html", context.edition_dir / f"DRAGON-{context.edition_date}.pdf")
        report = validate_pdf(path)
        report_path = context.run_dir / "qa" / "pdf.json"
        atomic_write_json(report_path, report)
        if report["status"] != "PASS":
            raise StageFailure("PDF_QA_FAILED", "; ".join(report["issues"]), outputs=(path, report_path))
        return StageResult((path, report_path))

    def epub(context: StageContext) -> StageResult:
        articles_value = [item for item in _load(context.edition_dir / "articles.json")["articles"] if item["status"] == "ACTIVE"]
        path = build_epub(context.edition_dir / f"DRAGON-{context.edition_date}.epub", context.edition_date, articles_value, context.edition_dir / "assets" / "cover.svg", mode=provider.mode)
        report = validate_epub(path)
        report_path = context.run_dir / "qa" / "epub.json"
        atomic_write_json(report_path, report)
        if report["status"] != "PASS":
            raise StageFailure("EPUB_QA_FAILED", "; ".join(report["issues"]), outputs=(path, report_path))
        return StageResult((path, report_path))

    def final_qa(context: StageContext) -> StageResult:
        plan = _load(context.edition_dir / "edition-plan.json")
        pdf_report = _load(context.run_dir / "qa" / "pdf.json")
        epub_report = _load(context.run_dir / "qa" / "epub.json")
        arabic_report = _load(context.run_dir / "qa" / "arabic-language.json")
        active = sum(item["status"] == "ACTIVE" for item in plan["section_inventory"])
        issues = []
        if active + sum(item["status"] == "SKIPPED" for item in plan["section_inventory"]) != len(SECTION_HEADINGS):
            issues.append("SECTION_INVENTORY_INCOMPLETE")
        for label, report in (("PDF", pdf_report), ("EPUB", epub_report), ("ARABIC", arabic_report)):
            if report["status"] != "PASS":
                issues.append(f"{label}_NOT_PASS")
        artifacts = [context.edition_dir / "edition.md", context.edition_dir / "edition.html", context.edition_dir / f"DRAGON-{context.edition_date}.pdf", context.edition_dir / f"DRAGON-{context.edition_date}.epub", context.edition_dir / "assets" / "cover.svg"]
        report = {"status": "PASS" if not issues else "FAIL", "mode": provider.mode, "active_sections": active, "issues": issues, **artifact_manifest(artifacts, context.root, mode=provider.mode)}
        report_path = context.edition_dir / "final-qa.json"
        atomic_write_json(report_path, report)
        manifest_path = context.edition_dir / "manifest.json"
        atomic_write_json(manifest_path, artifact_manifest(artifacts + [report_path], context.root, mode=provider.mode))
        if issues:
            raise StageFailure("FINAL_QA_FAILED", "; ".join(issues), outputs=(report_path, manifest_path))
        return StageResult((report_path, manifest_path), metadata={"state_updates": {"publication_status": "COMPLETE"}})

    def github_archive(context: StageContext) -> StageResult:
        receipt = context.run_dir / "archive-receipt.json"
        try:
            result = archive_provider.archive(context.root, context.edition_dir, context.edition_date)
        except ArchiveError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        atomic_write_json(receipt, {"stage": "github_archive", "mode": provider.mode, **result})
        status = result["status"]
        return StageResult((receipt,), status=status, metadata={"state_updates": {"archive_status": status}})

    def whatsapp_delivery(context: StageContext) -> StageResult:
        receipt = context.run_dir / "delivery-receipt.json"
        pdf_path = context.edition_dir / f"DRAGON-{context.edition_date}.pdf"
        try:
            result = whatsapp_provider.send(pdf_path, context.edition_date)
        except WhatsAppError as exc:
            raise StageFailure(exc.code, str(exc)) from exc
        atomic_write_json(receipt, {"stage": "whatsapp_delivery", "mode": provider.mode, **result})
        status = result["status"]
        return StageResult((receipt,), status=status, metadata={"state_updates": {"delivery_status": status}})

    preflight = synthetic_preflight_stage() if synthetic else preflight_stage()
    return [
        preflight,
        _json_stage("research", ("preflight",), research),
        _json_stage("article_generation", ("research",), articles),
        _json_stage("chief_editor", ("article_generation",), chief_editor),
        _json_stage("factcheck", ("chief_editor",), factcheck),
        _json_stage("arabic_language_qa", ("factcheck",), arabic_qa),
        _json_stage("cover", ("arabic_language_qa",), cover),
        _json_stage("publication_source", ("cover",), publication_source),
        _json_stage("pdf", ("publication_source",), pdf),
        _json_stage("epub", ("publication_source",), epub),
        _json_stage("final_qa", ("pdf", "epub"), final_qa),
        _json_stage("github_archive", ("final_qa",), github_archive),
        _json_stage("whatsapp_delivery", ("final_qa",), whatsapp_delivery),
    ]
