"""Concrete DRAGON V5 stages shared by production and synthetic acceptance runs."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from dragon.builtin_stages import preflight_stage
from dragon.archive import ArchiveError, DisabledGitArchiveProvider
from dragon.continuity import build_snapshot, prior_context
from dragon.editorial import adversarial_review, chief_editor_report, factcheck_report
from dragon.evidence import build_claim_graph, validate_claim_graph
from dragon.language import decode_utf8, validate_arabic_text
from dragon.investigations import InvestigationError, update_investigation_dossiers
from dragon.media_critic import build_media_critic, validate_media_critic
from dragon.providers import EditorialProvider, ProviderError, SECTION_HEADINGS
from dragon.research_planning import build_research_plan, validate_research_plan
from dragon.science import science_integrity_report, validate_science_report
from dragon.source_intelligence import build_source_intelligence
from dragon.publication import (
    artifact_manifest,
    build_epub,
    build_html,
    build_cover_png,
    render_pdf,
    validate_epub,
    validate_pdf,
    validate_publication_source,
)
from dragon.stages import StageContext, StageDefinition, StageFailure, StageResult
from dragon.state import atomic_write_json, runtime_fingerprint, sha256_file
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
        continuity = prior_context(context.root, context.edition_date)
        continuity_path = context.run_dir / "research" / "continuity-context.json"
        atomic_write_json(continuity_path, continuity)
        try:
            packet = provider.research(context.edition_date, continuity)
        except ProviderError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        packet["provider_mode"] = provider.mode
        path = context.run_dir / "research" / "research-packet.json"
        atomic_write_json(path, packet)
        return StageResult((continuity_path, path))

    def articles(context: StageContext) -> StageResult:
        packet = _load(context.run_dir / "research" / "research-packet.json")
        packet["source_intelligence"] = _load(
            context.run_dir / "source-intelligence" / "report.json"
        )
        packet["research_plan"] = _load(
            context.run_dir / "research-planning" / "plan.json"
        )
        try:
            values = provider.articles(packet)
        except ProviderError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        path = context.run_dir / "articles" / "articles.json"
        atomic_write_json(path, {"mode": provider.mode, "articles": values})
        return StageResult(
            (path,),
            inputs=(
                context.run_dir / "research" / "research-packet.json",
                context.run_dir / "source-intelligence" / "report.json",
                context.run_dir / "research-planning" / "plan.json",
            ),
        )

    def source_intelligence(context: StageContext) -> StageResult:
        packet_path = context.run_dir / "research" / "research-packet.json"
        report = build_source_intelligence(_load(packet_path))
        schema_path = Path(__file__).resolve().parents[1] / "config" / "source-intelligence-schema.json"
        schema = _load(schema_path)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(report),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            detail = "; ".join(error.message for error in errors[:5])
            raise StageFailure("SOURCE_INTELLIGENCE_INVALID", detail)
        path = context.run_dir / "source-intelligence" / "report.json"
        atomic_write_json(path, report)
        return StageResult((path,), inputs=(packet_path,))

    def research_planning(context: StageContext) -> StageResult:
        packet_path = context.run_dir / "research" / "research-packet.json"
        intelligence_path = context.run_dir / "source-intelligence" / "report.json"
        plan = build_research_plan(_load(packet_path), _load(intelligence_path))
        issues = validate_research_plan(
            plan, {section_id for section_id, _ in SECTION_HEADINGS}
        )
        if issues:
            raise StageFailure("RESEARCH_PLAN_INVALID", "; ".join(issues))
        path = context.run_dir / "research-planning" / "plan.json"
        atomic_write_json(path, plan)
        return StageResult((path,), inputs=(packet_path, intelligence_path))

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
        editorial = chief_editor_report(articles_value)
        plan["ranked_article_ids"] = editorial["ranked_article_ids"]
        plan["front_page_article_ids"] = editorial["front_page_article_ids"]
        editorial_path = context.run_dir / "editorial" / "chief-editor-report.json"
        atomic_write_json(editorial_path, editorial)
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
        if editorial["status"] != "PASS":
            raise StageFailure(
                "CHIEF_EDITOR_FAILED",
                "; ".join(editorial["issues"]),
                outputs=(editorial_path, plan_path, sources_path, markdown, canonical_articles),
            )
        return StageResult(
            (editorial_path, plan_path, sources_path, markdown, canonical_articles),
            inputs=(
                context.run_dir / "articles" / "articles.json",
                context.run_dir / "research" / "research-packet.json",
                context.run_dir / "evidence" / "claim-graph.json",
                context.run_dir / "editorial" / "adversarial-review.json",
                context.run_dir / "factcheck" / "report.json",
            ),
        )

    def claim_evidence_graph(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        intelligence_path = context.run_dir / "source-intelligence" / "report.json"
        articles_value = _load(articles_path)["articles"]
        graph = build_claim_graph(articles_value, _load(intelligence_path))
        issues = validate_claim_graph(graph, articles_value)
        if issues:
            raise StageFailure("CLAIM_GRAPH_INVALID", "; ".join(issues))
        path = context.run_dir / "evidence" / "claim-graph.json"
        atomic_write_json(path, graph)
        return StageResult((path,), inputs=(articles_path, intelligence_path))

    def adversarial(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        graph_path = context.run_dir / "evidence" / "claim-graph.json"
        plan_path = context.run_dir / "research-planning" / "plan.json"
        media_path = context.run_dir / "media-critic" / "report.json"
        report = adversarial_review(
            _load(articles_path)["articles"], _load(graph_path), _load(plan_path),
            _load(media_path),
        )
        path = context.run_dir / "editorial" / "adversarial-review.json"
        atomic_write_json(path, report)
        if report["status"] != "PASS":
            raise StageFailure(
                "ADVERSARIAL_REVIEW_FAILED", "; ".join(report["issues"]), outputs=(path,)
            )
        return StageResult((path,), inputs=(articles_path, graph_path, plan_path, media_path))

    def media_critic(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        plan_path = context.run_dir / "research-planning" / "plan.json"
        intelligence_path = context.run_dir / "source-intelligence" / "report.json"
        articles_value = _load(articles_path)["articles"]
        report = build_media_critic(
            articles_value, _load(plan_path), _load(intelligence_path)
        )
        issues = validate_media_critic(report, articles_value)
        if issues:
            raise StageFailure("MEDIA_CRITIC_INVALID", "; ".join(issues))
        path = context.run_dir / "media-critic" / "report.json"
        atomic_write_json(path, report)
        return StageResult((path,), inputs=(articles_path, plan_path, intelligence_path))

    def science_integrity(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        intelligence_path = context.run_dir / "source-intelligence" / "report.json"
        report = science_integrity_report(
            _load(articles_path)["articles"], _load(intelligence_path)
        )
        structural_issues = validate_science_report(
            report, _load(articles_path)["articles"]
        )
        if structural_issues:
            raise StageFailure("SCIENCE_REPORT_INVALID", "; ".join(structural_issues))
        path = context.run_dir / "science" / "integrity-report.json"
        atomic_write_json(path, report)
        if report["status"] != "PASS":
            raise StageFailure(
                "SCIENCE_INTEGRITY_FAILED", "; ".join(report["issues"]), outputs=(path,)
            )
        return StageResult((path,), inputs=(articles_path, intelligence_path))

    def investigation_engine(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        graph_path = context.run_dir / "evidence" / "claim-graph.json"
        intelligence_path = context.run_dir / "source-intelligence" / "report.json"
        try:
            report, dossier_paths = update_investigation_dossiers(
                context.root,
                context.edition_date,
                _load(articles_path)["articles"],
                _load(graph_path),
                _load(intelligence_path),
                synthetic=synthetic,
            )
        except InvestigationError as exc:
            raise StageFailure("INVESTIGATION_DOSSIER_INVALID", str(exc)) from exc
        path = context.run_dir / "investigations" / "readiness-report.json"
        atomic_write_json(path, report)
        outputs = (path, *dossier_paths)
        if report["status"] != "PASS":
            raise StageFailure(
                "INVESTIGATION_GATE_FAILED",
                "not publication ready: " + ",".join(report["not_ready_article_ids"]),
                outputs=outputs,
            )
        return StageResult(outputs, inputs=(articles_path, graph_path, intelligence_path))

    def factcheck(context: StageContext) -> StageResult:
        articles_path = context.run_dir / "articles" / "articles.json"
        research_path = context.run_dir / "research" / "research-packet.json"
        articles_value = _load(articles_path)["articles"]
        sources = _load(research_path)["sources"]
        report = factcheck_report(articles_value, sources, synthetic=synthetic)
        report["mode"] = provider.mode
        report["warning"] = "الاختبار الاصطناعي لا يثبت صحة أخبار حقيقية" if synthetic else None
        path = context.run_dir / "factcheck" / "report.json"
        atomic_write_json(path, report)
        if report["status"] != "PASS":
            raise StageFailure("ARTICLE_FACTCHECK_FAILED", "; ".join(report["issues"]), outputs=(path,))
        return StageResult(
            (path,),
            inputs=(
                articles_path,
                research_path,
                context.run_dir / "evidence" / "claim-graph.json",
                context.run_dir / "editorial" / "adversarial-review.json",
            ),
        )

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
        return StageResult(
            (path,), inputs=(context.edition_dir / "articles.json",)
        )

    def cover(context: StageContext) -> StageResult:
        decisions = _load(context.edition_dir / "articles.json")["articles"]
        plan = _load(context.edition_dir / "edition-plan.json")
        lead_id = next(iter(plan.get("front_page_article_ids", [])), None)
        lead = next((item for item in decisions if item.get("id") == lead_id), None)
        if lead is None:
            raise StageFailure("COVER_FAILED", "no active final-edition story is available")
        path = build_cover_png(
            context.edition_dir / "assets" / "cover.png",
            context.edition_date,
            lead["headline"],
            lead["standfirst"],
            mode=provider.mode,
        )
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
                dimensions = image.size
        except Exception as exc:
            raise StageFailure("COVER_FAILED", str(exc), outputs=(path,)) from exc
        if dimensions != (827, 1169):
            raise StageFailure("COVER_FAILED", f"unexpected dimensions {dimensions}", outputs=(path,))
        brief = context.edition_dir / "cover-brief.json"
        atomic_write_json(
            brief,
            {
                "mode": provider.mode,
                "cover_status": "COVER_FALLBACK",
                "asset_type": "DETERMINISTIC_PNG_FALLBACK",
                "canonical": "assets/cover.png",
                "accepted": True,
                "source_article_id": lead["id"],
                "headline": lead["headline"],
                "warning": "غلاف اختبار اصطناعي" if synthetic else None,
            },
        )
        return StageResult(
            (path, brief), inputs=(context.edition_dir / "edition-plan.json",)
        )

    def publication_source(context: StageContext) -> StageResult:
        articles_value = [item for item in _load(context.edition_dir / "articles.json")["articles"] if item["status"] == "ACTIVE"]
        path = build_html(context.edition_dir, context.edition_date, articles_value, mode=provider.mode)
        document = decode_utf8(path.read_bytes())
        issues = validate_publication_source(document, articles_value)
        if issues:
            raise StageFailure("PUBLICATION_SOURCE_INVALID", "; ".join(issues), outputs=(path,))
        return StageResult(
            (path, context.edition_dir / "print-v5.css"),
            inputs=(
                context.edition_dir / "articles.json",
                context.edition_dir / "edition-plan.json",
                context.edition_dir / "assets" / "cover.png",
            ),
        )

    def pdf(context: StageContext) -> StageResult:
        path = render_pdf(context.edition_dir / "edition.html", context.edition_dir / f"DRAGON-{context.edition_date}.pdf")
        active_count = sum(
            item["status"] == "ACTIVE"
            for item in _load(context.edition_dir / "articles.json")["articles"]
        )
        report = validate_pdf(
            path,
            minimum_pages=active_count + 1,
            canonical_cover=context.edition_dir / "assets" / "cover.png",
            expected_source_urls=tuple(
                url
                for item in _load(context.edition_dir / "articles.json")["articles"]
                if item["status"] == "ACTIVE"
                for url in item["source_urls"]
            ),
        )
        report_path = context.run_dir / "qa" / "pdf.json"
        atomic_write_json(report_path, report)
        if report["status"] != "PASS":
            raise StageFailure("PDF_QA_FAILED", "; ".join(report["issues"]), outputs=(path, report_path))
        return StageResult(
            (path, report_path),
            inputs=(
                context.edition_dir / "edition.html",
                context.edition_dir / "print-v5.css",
                context.edition_dir / "assets" / "cover.png",
                context.edition_dir / "articles.json",
            ),
        )

    def epub(context: StageContext) -> StageResult:
        articles_value = [item for item in _load(context.edition_dir / "articles.json")["articles"] if item["status"] == "ACTIVE"]
        path = build_epub(context.edition_dir / f"DRAGON-{context.edition_date}.epub", context.edition_date, articles_value, context.edition_dir / "assets" / "cover.png", mode=provider.mode)
        report = validate_epub(
            path,
            canonical_cover=context.edition_dir / "assets" / "cover.png",
            expected_article_ids=tuple(item["id"] for item in articles_value),
            expected_source_urls=tuple(
                url for item in articles_value for url in item["source_urls"]
            ),
        )
        report_path = context.run_dir / "qa" / "epub.json"
        atomic_write_json(report_path, report)
        if report["status"] != "PASS":
            raise StageFailure("EPUB_QA_FAILED", "; ".join(report["issues"]), outputs=(path, report_path))
        return StageResult(
            (path, report_path),
            inputs=(
                context.edition_dir / "articles.json",
                context.edition_dir / "assets" / "cover.png",
            ),
        )

    def final_qa(context: StageContext) -> StageResult:
        plan = _load(context.edition_dir / "edition-plan.json")
        pdf_report = _load(context.run_dir / "qa" / "pdf.json")
        epub_report = _load(context.run_dir / "qa" / "epub.json")
        arabic_report = _load(context.run_dir / "qa" / "arabic-language.json")
        editorial_report = _load(
            context.run_dir / "editorial" / "chief-editor-report.json"
        )
        factcheck_report_value = _load(context.run_dir / "factcheck" / "report.json")
        cover_brief = _load(context.edition_dir / "cover-brief.json")
        active = sum(item["status"] == "ACTIVE" for item in plan["section_inventory"])
        issues = []
        if active + sum(item["status"] == "SKIPPED" for item in plan["section_inventory"]) != len(SECTION_HEADINGS):
            issues.append("SECTION_INVENTORY_INCOMPLETE")
        for label, report in (
            ("EDITORIAL", editorial_report),
            ("FACTCHECK", factcheck_report_value),
            ("PDF", pdf_report),
            ("EPUB", epub_report),
            ("ARABIC", arabic_report),
        ):
            if report["status"] != "PASS":
                issues.append(f"{label}_NOT_PASS")
        if (
            cover_brief.get("cover_status") not in {"COVER_GENERATED", "COVER_FALLBACK"}
            or not cover_brief.get("accepted")
        ):
            issues.append("COVER_NOT_ACCEPTED")
        decisions = _load(context.edition_dir / "articles.json")["articles"]
        continuity_path = context.edition_dir / "continuity.json"
        atomic_write_json(
            continuity_path,
            build_snapshot(context.edition_date, provider.mode, decisions),
        )
        source_artifacts = [
            context.edition_dir / "edition.md",
            context.edition_dir / "edition.html",
            context.edition_dir / "edition-plan.json",
            context.edition_dir / "articles.json",
            context.edition_dir / "sources.json",
            context.edition_dir / "cover-brief.json",
            context.edition_dir / f"DRAGON-{context.edition_date}.pdf",
            context.edition_dir / f"DRAGON-{context.edition_date}.epub",
            context.edition_dir / "assets" / "cover.png",
        ]
        artifacts = source_artifacts + [continuity_path]
        report = {
            "status": "PASS" if not issues else "FAIL",
            "mode": provider.mode,
            "active_sections": active,
            "editorial_status": editorial_report["status"],
            "factcheck_status": factcheck_report_value["status"],
            "arabic_status": arabic_report["status"],
            "pdf_status": pdf_report["status"],
            "epub_status": epub_report["status"],
            "cover_status": cover_brief.get("cover_status"),
            "issues": issues,
            **artifact_manifest(artifacts, context.root, mode=provider.mode),
        }
        report_path = context.edition_dir / "final-qa.json"
        atomic_write_json(report_path, report)
        manifest_path = context.edition_dir / "manifest.json"
        atomic_write_json(manifest_path, artifact_manifest(artifacts + [report_path], context.root, mode=provider.mode))
        if issues:
            raise StageFailure("FINAL_QA_FAILED", "; ".join(issues), outputs=(report_path, manifest_path))
        return StageResult(
            (report_path, manifest_path),
            metadata={"state_updates": {"publication_status": "COMPLETE"}},
            inputs=tuple(source_artifacts)
            + (
                context.run_dir / "qa" / "pdf.json",
                context.run_dir / "qa" / "epub.json",
                context.run_dir / "qa" / "arabic-language.json",
                context.run_dir / "editorial" / "chief-editor-report.json",
                context.run_dir / "factcheck" / "report.json",
            ),
        )

    def github_archive(context: StageContext) -> StageResult:
        receipt = context.run_dir / "archive-receipt.json"
        manifest_path = context.edition_dir / "manifest.json"
        try:
            result = archive_provider.archive(context.root, context.edition_dir, context.edition_date)
        except ArchiveError as exc:
            raise StageFailure(exc.code, exc.detail) from exc
        atomic_write_json(
            receipt,
            {
                "schema_version": 5,
                "stage": "github_archive",
                "mode": provider.mode,
                "edition_date": context.edition_date,
                "runtime_fingerprint": runtime_fingerprint(context.root),
                "publication_status": "COMPLETE",
                "manifest_sha256": sha256_file(manifest_path),
                **result,
            },
        )
        status = result["status"]
        return StageResult(
            (receipt,),
            status=status,
            metadata={"state_updates": {"archive_status": status}},
            inputs=(manifest_path,),
        )

    def whatsapp_delivery(context: StageContext) -> StageResult:
        receipt = context.run_dir / "delivery-receipt.json"
        pdf_path = context.edition_dir / f"DRAGON-{context.edition_date}.pdf"
        prior = None
        if receipt.is_file():
            try:
                prior = _load(receipt)
            except (OSError, json.JSONDecodeError):
                prior = None
        try:
            plan = _load(context.edition_dir / "edition-plan.json")
            decisions = _load(context.edition_dir / "articles.json")["articles"]
            ranked = plan.get("front_page_article_ids", [])
            headlines_by_id = {
                item["id"]: item["headline"]
                for item in decisions
                if item.get("status") == "ACTIVE"
            }
            lead_headlines = tuple(
                headlines_by_id[article_id]
                for article_id in ranked
                if article_id in headlines_by_id
            )
            result = whatsapp_provider.send(
                pdf_path,
                context.edition_date,
                prior,
                lead_headlines,
            )
        except WhatsAppError as exc:
            outputs = ()
            if exc.partial_receipt:
                atomic_write_json(
                    receipt,
                    {
                        "schema_version": 5,
                        "stage": "whatsapp_delivery",
                        "mode": provider.mode,
                        "edition_date": context.edition_date,
                        "runtime_fingerprint": runtime_fingerprint(context.root),
                        "publication_status": "COMPLETE",
                        **exc.partial_receipt,
                    },
                )
                outputs = (receipt,)
            raise StageFailure(exc.code, str(exc), outputs=outputs) from exc
        atomic_write_json(
            receipt,
            {
                "schema_version": 5,
                "stage": "whatsapp_delivery",
                "mode": provider.mode,
                "edition_date": context.edition_date,
                "runtime_fingerprint": runtime_fingerprint(context.root),
                "publication_status": "COMPLETE",
                **result,
            },
        )
        status = result["status"]
        return StageResult(
            (receipt,),
            status=status,
            metadata={"state_updates": {"delivery_status": status}},
            inputs=(
                pdf_path,
                context.edition_dir / "edition-plan.json",
                context.edition_dir / "articles.json",
            ),
        )

    preflight = synthetic_preflight_stage() if synthetic else preflight_stage()
    return [
        preflight,
        _json_stage("research", ("preflight",), research),
        _json_stage("source_intelligence", ("research",), source_intelligence),
        _json_stage("research_planning", ("source_intelligence",), research_planning),
        _json_stage("article_generation", ("research_planning",), articles),
        _json_stage("claim_evidence_graph", ("article_generation",), claim_evidence_graph),
        _json_stage("media_critic", ("claim_evidence_graph",), media_critic),
        _json_stage("science_integrity", ("media_critic",), science_integrity),
        _json_stage("investigation_engine", ("science_integrity",), investigation_engine),
        _json_stage("adversarial_review", ("investigation_engine",), adversarial),
        _json_stage("factcheck", ("adversarial_review",), factcheck),
        _json_stage("chief_editor", ("factcheck",), chief_editor),
        _json_stage("arabic_language_qa", ("chief_editor",), arabic_qa),
        _json_stage("cover", ("arabic_language_qa",), cover),
        _json_stage("publication_source", ("cover",), publication_source),
        _json_stage("pdf", ("publication_source",), pdf),
        _json_stage("epub", ("publication_source",), epub),
        _json_stage("final_qa", ("pdf", "epub"), final_qa),
        _json_stage("github_archive", ("final_qa",), github_archive),
        _json_stage("whatsapp_delivery", ("final_qa",), whatsapp_delivery),
    ]
