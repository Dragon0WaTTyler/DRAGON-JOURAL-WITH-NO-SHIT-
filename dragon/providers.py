"""Editorial provider boundary for production and explicit fixture runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
from string import Formatter
import subprocess
import sys
import re
from typing import Protocol
from urllib.parse import urlparse


class EditorialProvider(Protocol):
    mode: str

    def research(self, edition_date: str, continuity: dict | None = None) -> dict: ...

    def articles(self, research: dict) -> list[dict]: ...


class ProviderError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class UnconfiguredEditorialProvider:
    mode: str = "production"
    reason: str = "AI_PROVIDER_UNCONFIGURED"
    available: bool = False

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        raise ProviderError(self.reason, "no proven unattended editorial provider")

    def articles(self, research: dict) -> list[dict]:
        raise ProviderError(self.reason, "no proven unattended editorial provider")


SECTION_HEADINGS = (
    ("front", "الواجهة"),
    ("siyasa_dawla", "السياسة والدولة"),
    ("iqtisad_flous", "الاقتصاد والمال"),
    ("mojtama3", "المجتمع"),
    ("ta3lim", "التعليم"),
    ("se77a", "الصحة"),
    ("3adl_7o9o9", "العدالة والحقوق"),
    ("bi2a_manakh", "البيئة والمناخ"),
    ("bniya_transport", "البنية التحتية والنقل"),
    ("meknes_local", "مكناس وفاس مكناس"),
    ("filastin_middle_east", "فلسطين والشرق الأوسط"),
    ("africa_sahel", "أفريقيا والساحل"),
    ("world", "العالم"),
    ("business_companies", "الأعمال والشركات"),
    ("technology", "الذكاء الاصطناعي والتكنولوجيا"),
    ("science", "العلوم والدراسات"),
    ("sport", "الرياضة"),
    ("culture", "الثقافة"),
    ("adab", "الأدب"),
    ("history", "تاريخ المغرب والمغرب الكبير"),
    ("investigations", "التحقيق والمساءلة"),
    ("opinion", "رأي"),
    ("service", "البيانات والخدمات وما نتابعه"),
)

STORY_TYPES = {
    "NEWS", "ANALYSIS", "INVESTIGATION", "SCIENCE", "HISTORY", "CULTURE",
    "FACT_CHECK", "DATA", "DOCUMENT_PUBLIC_RECORD", "SECTION_OPENER",
}


def _synthetic_story_type(section_id: str) -> str:
    return {
        "investigations": "INVESTIGATION",
        "science": "SCIENCE",
        "history": "HISTORY",
        "culture": "CULTURE",
        "adab": "CULTURE",
        "opinion": "ANALYSIS",
        "service": "DATA",
    }.get(section_id, "NEWS")


@dataclass(frozen=True)
class SyntheticEditorialProvider:
    """Deterministic, clearly labelled fixture data; never a news source."""

    mode: str = "synthetic"
    available: bool = True
    byline: str = "تحرير: DRAGON"

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        packet = {
            "mode": self.mode,
            "edition_date": edition_date,
            "warning": "بيانات اختبار اصطناعية، وليست أخبارا أو وقائع للنشر",
            "sources": [
                {
                    "id": "fixture-source",
                    "title": "مصدر تجريبي غير صحفي",
                    "url": "https://example.org/dragon-fixture",
                    "retrieved_at": f"{edition_date}T07:00:00+01:00",
                    "publisher": "نطاق الأمثلة المحجوز",
                    "publication_date": edition_date,
                    "accessed_at": f"{edition_date}T07:00:00+01:00",
                    "source_type": "synthetic",
                    "claim_supported": "لا يوجد ادعاء واقعي؛ مصدر محجوز للاختبار",
                    "doi": None,
                    "publication_status": "not_applicable",
                    "full_text_status": "NOT_APPLICABLE",
                    "methods_read": False,
                    "limitations_read": False,
                    "science_metadata": None,
                }
            ],
        }
        packet["sections"] = []
        for section_id, heading in SECTION_HEADINGS:
            candidates = [
                {
                    "id": f"{section_id}-candidate-{number}",
                    "rank": number,
                    "title": f"مرشح اختبار {number} لقسم {heading}",
                    "discovery_source_ids": ["fixture-source"],
                    "verification_source_ids": ["fixture-source"],
                    "primary_evidence_source_ids": ["fixture-source"],
                    "independent_evidence_source_ids": [],
                    "facts": ["لا توجد حقيقة صحفية؛ هذا مرشح اصطناعي"],
                    "claims": [],
                    "unknowns": [],
                    "disputed_points": [],
                }
                for number in (1, 2)
            ]
            packet["sections"].append(
                {
                    "section_id": section_id,
                    "status": "ACTIVE",
                    "candidates": candidates,
                    "selected_candidate_id": candidates[0]["id"],
                    "selection_reason": "اختيار ثابت لاختبار خط الإنتاج فقط",
                    "no_news_reason": None,
                    "fallback_action": None,
                }
            )
        return packet

    def articles(self, research: dict) -> list[dict]:
        date_value = research["edition_date"]
        articles: list[dict] = []
        for index, (section_id, heading) in enumerate(SECTION_HEADINGS, start=1):
            body = [
                "هذه فقرة عربية مصطنعة صممت لاختبار سلامة الترميز واتجاه القراءة وتسلسل الصفحات. لا تتضمن الفقرة ادعاء واقعيا، ولا يجوز تقديمها إلى القارئ بوصفها تغطية صحفية.",
                f"يسجل هذا النموذج تاريخ النسخة \u200e{date_value}\u200e ويختبر وجود عنوان القسم والمتن والمصدر وحالة المادة. الغرض تقني بحت، وتبقى مرحلة الإنتاج الحقيقي متوقفة إلى حين تهيئة مزود تحريري موثوق.",
                "تتحقق بوابة الجودة من العربية السليمة، ومن غياب أحرف الترميز التالفة، ومن اتصال كل مادة بمصدر ظاهر. كما تحفظ النتائج في ملفات قابلة للتدقيق والاستئناف.",
            ]
            body.extend(
                f"فقرة القياس رقم {number} مادة اختبارية واضحة لا تضيف واقعة أو اتهاما أو اقتباسا. وظيفتها قياس تدفق السطور والهوامش والأعمدة ومنع القص والصفحات الفارغة مع إبقاء التحذير الاصطناعي ظاهرا في كل مرحلة من مراحل النسخة."
                for number in range(1, 13)
            )
            articles.append(
                {
                    "id": f"fixture-{index:02d}",
                    "section_id": section_id,
                    "section": heading,
                    "status": "ACTIVE",
                    "headline": f"مادة اختبارية لقسم {heading}",
                    "standfirst": "نص اصطناعي ثابت للتحقق من سير التحرير والطباعة، ولا يمثل خبرا حقيقيا.",
                    "byline": self.byline,
                    "body": body,
                    "source_ids": ["fixture-source"],
                    "research_candidate_id": f"{section_id}-candidate-1",
                    "story_key": f"synthetic-{section_id}-{date_value}",
                    "story_type": _synthetic_story_type(section_id),
                    "claims": [
                        {
                            "text": "المادة اصطناعية وغير خبرية",
                            "classification": "FACT",
                            "claim_type": "general",
                            "attribution": "بيان تقني داخل النسخة",
                            "source_ids": ["fixture-source"],
                            "material": False,
                        }
                    ],
                    "editorial_elements": {
                        "lead": "توضيح غرض المادة الاختبارية",
                        "nut_graf": "الهدف هو التحقق التقني من دورة النشر",
                        "verified_facts": ["المحتوى مصطنع بوضوح"],
                        "context": "اختبار قبول محلي",
                        "uncertainty": "لا توجد ادعاءات واقعية",
                        "consequences": "لا يجوز توزيع النسخة كصحيفة حقيقية",
                        "next_steps": "تهيئة مزود إنتاج موثوق قبل النشر",
                    },
                    "investigation_checks": {
                        "serious_accountability_claim": False,
                        "counter_evidence_checked": False,
                        "response_status": "NOT_APPLICABLE",
                        "publication_ready": True,
                    } if section_id == "investigations" else None,
                    "fixture": True,
                }
            )
        return articles


def _https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.path not in {"", "/"}


def _valid_science_metadata(value: object) -> bool:
    required = {
        "paper_id", "title", "authors", "journal", "version_type", "sample",
        "sample_size", "design", "effect_result", "statistics",
        "corrections_retractions", "conflicting_study_source_ids", "locators",
        "confidence", "doi_verified", "metadata_matches", "claim_alignment",
        "correlation_only",
    }
    if not isinstance(value, dict) or set(value) != required:
        return False
    return (
        all(
            value[field] is None or isinstance(value[field], str)
            for field in (
                "paper_id", "title", "journal", "sample", "design",
                "effect_result", "statistics",
            )
        )
        and isinstance(value["authors"], list)
        and all(isinstance(item, str) for item in value["authors"])
        and all(
            isinstance(value[field], list)
            and all(isinstance(item, str) for item in value[field])
            for field in (
                "corrections_retractions", "conflicting_study_source_ids", "locators"
            )
        )
        and value["version_type"] in {
            "PREPRINT", "ACCEPTED_MANUSCRIPT", "VERSION_OF_RECORD", "UNKNOWN", None
        }
        and value["confidence"] in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
        and value["claim_alignment"] in {
            "ALIGNED", "PARTIAL", "MISALIGNED", "NOT_ASSESSED"
        }
        and (
            value["sample_size"] is None
            or isinstance(value["sample_size"], int) and value["sample_size"] >= 0
        )
        and all(
            isinstance(value[field], bool)
            for field in ("doi_verified", "metadata_matches", "correlation_only")
        )
    )


@dataclass(frozen=True)
class LocalCommandEditorialProvider:
    """JSON stdin/stdout adapter for an explicitly configured local runtime."""

    command: tuple[str, ...]
    timeout_seconds: int = 7200
    minimum_active_article_words: int = 350
    minimum_edition_words: int = 4000
    expected_byline: str = "تحرير: DRAGON"
    capture_directory: Path | None = None
    mode: str = "production"
    available: bool = True

    def _capture(self, filename: str, value: object) -> None:
        if self.capture_directory is None:
            return
        self.capture_directory.mkdir(parents=True, exist_ok=True)
        path = self.capture_directory / filename
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _invoke(self, operation: str, payload: dict) -> dict | list:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                [*self.command, "--operation", operation],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProviderError("AI_PROVIDER_EXECUTION_FAILED", str(exc)) from exc
        if result.returncode:
            detail = result.stderr.strip()[:2000] or f"provider exited {result.returncode}"
            raise ProviderError("AI_PROVIDER_EXECUTION_FAILED", detail)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("AI_PROVIDER_RESPONSE_INVALID", "provider stdout is not one JSON value") from exc
        if operation in {"research", "articles"}:
            self._capture(f"{operation}.raw.json", value)
        return value

    def healthcheck(self) -> dict:
        value = self._invoke("healthcheck", {"schema_version": 5})
        if not isinstance(value, dict) or value.get("status") != "PASS" or value.get("unattended") is not True:
            raise ProviderError("AI_PROVIDER_HEALTHCHECK_FAILED", "provider did not prove unattended capability")
        return value

    def research(self, edition_date: str, continuity: dict | None = None) -> dict:
        value = self._invoke(
            "research",
            {
                "schema_version": 5,
                "edition_date": edition_date,
                "language": "ar",
                "continuity": continuity or {"edition_count": 0, "editions": []},
            },
        )
        if not isinstance(value, dict) or value.get("edition_date") != edition_date:
            raise ProviderError("RESEARCH_PACKET_INVALID", "date or root object is invalid")
        sources = value.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ProviderError("RESEARCH_PACKET_INVALID", "sources must be a non-empty list")
        identifiers = set()
        required_source_fields = (
            "id",
            "url",
            "publisher",
            "publication_date",
            "accessed_at",
            "source_type",
            "claim_supported",
            "doi",
            "publication_status",
            "full_text_status",
            "methods_read",
            "limitations_read",
            "science_metadata",
        )
        for source in sources:
            if (
                not isinstance(source, dict)
                or any(field not in source for field in required_source_fields)
                or any(
                    not source.get(field)
                    for field in (
                        "id", "url", "publisher", "publication_date", "accessed_at",
                        "source_type", "claim_supported", "publication_status",
                        "full_text_status",
                    )
                )
                or not isinstance(source.get("id"), str)
                or not _https_url(source.get("url"))
                or source.get("publication_status") not in {
                    "peer_reviewed", "preprint", "report", "news", "not_applicable", "unknown"
                }
                or source.get("full_text_status") not in {
                    "FULL_TEXT_VERIFIED", "ABSTRACT_ONLY", "FULL_TEXT_UNAVAILABLE",
                    "NOT_APPLICABLE", "UNKNOWN",
                }
                or not isinstance(source.get("methods_read"), bool)
                or not isinstance(source.get("limitations_read"), bool)
                or (
                    source.get("full_text_status") != "FULL_TEXT_VERIFIED"
                    and (source.get("methods_read") or source.get("limitations_read"))
                )
                or (
                    source.get("science_metadata") is not None
                    and not _valid_science_metadata(source.get("science_metadata"))
                )
            ):
                raise ProviderError(
                    "RESEARCH_PACKET_INVALID",
                    "every source needs provenance, claim support, and an exact HTTPS page URL",
                )
            if source["id"] in identifiers:
                raise ProviderError("RESEARCH_PACKET_INVALID", "source ids must be unique")
            identifiers.add(source["id"])
        sections = value.get("sections")
        expected_sections = {section_id for section_id, _ in SECTION_HEADINGS}
        observed_ids = [
            item.get("section_id") for item in sections if isinstance(item, dict)
        ] if isinstance(sections, list) else []
        observed_set = set(observed_ids)
        if (
            not isinstance(sections, list)
            or len(sections) != len(expected_sections)
            or observed_set != expected_sections
        ):
            counts = Counter(observed_ids)
            missing = sorted(expected_sections - observed_set)
            unknown = sorted(str(item) for item in observed_set - expected_sections)
            duplicates = sorted(str(item) for item, count in counts.items() if count > 1)
            invalid_entries = (
                sum(not isinstance(item, dict) for item in sections)
                if isinstance(sections, list)
                else 0
            )
            raise ProviderError(
                "RESEARCH_PACKET_INVALID",
                "research must contain one candidate decision for every section; "
                f"count={len(sections) if isinstance(sections, list) else 'not-list'}; "
                f"missing={missing}; unknown={unknown}; duplicates={duplicates}; "
                f"invalid_entries={invalid_entries}",
            )
        for section in sections:
            section_status = section.get("status")
            if section_status not in {"ACTIVE", "NO_NEWS"}:
                raise ProviderError(
                    "RESEARCH_PACKET_INVALID",
                    f"section {section.get('section_id')} needs ACTIVE or NO_NEWS status",
                )
            candidates = section.get("candidates")
            minimum_candidates = 2 if section_status == "ACTIVE" else 0
            if not isinstance(candidates, list) or len(candidates) < minimum_candidates:
                raise ProviderError(
                    "RESEARCH_PACKET_INVALID",
                    f"active section {section.get('section_id')} needs at least two ranked candidates",
                )
            candidate_ids = set()
            for candidate in candidates:
                required_candidate_fields = (
                    "id",
                    "rank",
                    "title",
                    "discovery_source_ids",
                    "verification_source_ids",
                    "primary_evidence_source_ids",
                    "independent_evidence_source_ids",
                    "facts",
                    "claims",
                    "unknowns",
                    "disputed_points",
                )
                if not isinstance(candidate, dict) or any(
                    field not in candidate for field in required_candidate_fields
                ):
                    raise ProviderError(
                        "RESEARCH_PACKET_INVALID",
                        f"candidate structure is incomplete in {section.get('section_id')}",
                    )
                evidence_fields = (
                    "discovery_source_ids",
                    "verification_source_ids",
                    "primary_evidence_source_ids",
                    "independent_evidence_source_ids",
                )
                content_fields = ("facts", "claims", "unknowns", "disputed_points")
                if (
                    not isinstance(candidate["id"], str)
                    or not candidate["id"].strip()
                    or candidate["id"] in candidate_ids
                    or not isinstance(candidate["rank"], int)
                    or candidate["rank"] < 1
                    or any(not isinstance(candidate[field], list) for field in evidence_fields)
                    or any(not isinstance(candidate[field], list) for field in content_fields)
                ):
                    raise ProviderError(
                        "RESEARCH_PACKET_INVALID",
                        f"candidate types or identity are invalid in {section.get('section_id')}",
                    )
                candidate_ids.add(candidate["id"])
                referenced = set(candidate["discovery_source_ids"]) | set(
                    candidate["verification_source_ids"]
                ) | set(candidate["primary_evidence_source_ids"]) | set(
                    candidate["independent_evidence_source_ids"]
                )
                if not referenced or not referenced.issubset(identifiers):
                    raise ProviderError(
                        "RESEARCH_PACKET_INVALID",
                        f"candidate {candidate['id']} cites unknown evidence",
                    )
            selected = section.get("selected_candidate_id")
            if section_status == "NO_NEWS":
                reason = section.get("no_news_reason")
                if (
                    candidates
                    or selected is not None
                    or section.get("selection_reason") is not None
                    or not isinstance(reason, str)
                    or len(reason.strip()) < 10
                    or section.get("fallback_action") not in {
                        "RADAR", "DOSSIER_FOLLOW_UP", "PUBLIC_DATA_ANALYSIS", "SKIP"
                    }
                ):
                    raise ProviderError(
                        "RESEARCH_PACKET_INVALID",
                        f"no-news section {section.get('section_id')} must have no fabricated candidates and a specific fallback",
                    )
            elif (
                selected not in candidate_ids
                or not isinstance(section.get("selection_reason"), str)
                or len(section["selection_reason"].strip()) < 10
                or section.get("no_news_reason") is not None
                or section.get("fallback_action") is not None
            ):
                raise ProviderError(
                    "RESEARCH_PACKET_INVALID",
                    f"section {section.get('section_id')} has no justified selected lead",
                )
        return value

    def articles(self, research: dict) -> list[dict]:
        payload = {
            "schema_version": 5,
            "research": research,
            "language": "ar",
            "quality_constraints": {
                "minimum_active_article_words": self.minimum_active_article_words,
                "minimum_edition_words": self.minimum_edition_words,
            },
            "editorial_identity": {"expected_byline": self.expected_byline},
        }
        value = self._invoke("articles", payload)
        try:
            return self._validate_articles(value, research)
        except ProviderError as exc:
            if exc.code != "ARTICLE_SCHEMA_INVALID":
                raise
            self._capture("articles.attempt-1.raw.json", value)
            repaired = self._invoke(
                "articles",
                {
                    **payload,
                    "repair_context": {
                        "attempt": 2,
                        "maximum_attempts": 2,
                        "validation_error": exc.detail,
                        "previous_articles": value,
                        "instruction": (
                            "Preserve valid decisions verbatim, repair only invalid decisions, "
                            "and return the complete articles wrapper."
                        ),
                    },
                },
            )
            return self._validate_articles(repaired, research)

    def _validate_articles(self, value: object, research: dict) -> list[dict]:
        if not isinstance(value, list):
            raise ProviderError("ARTICLE_SCHEMA_INVALID", "provider must return an article/skip list")
        expected = {section_id for section_id, _ in SECTION_HEADINGS}
        sources = {item["id"] for item in research["sources"]}
        research_sections = {
            item["section_id"]: item for item in research.get("sections", [])
        }
        seen = set()
        edition_words = 0
        active_count = 0
        required_elements = (
            "lead",
            "nut_graf",
            "verified_facts",
            "context",
            "uncertainty",
            "consequences",
            "next_steps",
        )
        for item in value:
            if not isinstance(item, dict) or item.get("section_id") not in expected:
                raise ProviderError("ARTICLE_SCHEMA_INVALID", "unknown or missing section_id")
            section_id = item["section_id"]
            if section_id in seen:
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"duplicate section {section_id}")
            seen.add(section_id)
            status = item.get("status")
            if status == "SKIPPED":
                if not isinstance(item.get("skip_reason"), str) or len(item["skip_reason"].strip()) < 10:
                    raise ProviderError("ARTICLE_SCHEMA_INVALID", f"section {section_id} needs a specific skip reason")
                continue
            research_section = research_sections.get(section_id, {})
            if research_section.get("status") == "NO_NEWS":
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID",
                    f"no-news research section {section_id} cannot become an active article",
                )
            required = (
                "id", "section", "headline", "standfirst", "byline", "body",
                "source_ids", "story_type",
            )
            if status != "ACTIVE" or any(not item.get(field) for field in required):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"active section {section_id} is incomplete")
            if item["byline"] != self.expected_byline:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID",
                    f"article {item.get('id')} byline does not match configured editorial identity",
                )
            if not isinstance(item["body"], list) or not all(isinstance(paragraph, str) for paragraph in item["body"]):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} body is invalid")
            if not isinstance(item["source_ids"], list) or not set(item["source_ids"]).issubset(sources):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} cites unknown sources")
            selected = research_section.get("selected_candidate_id")
            if item.get("research_candidate_id") != selected:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID",
                    f"article {item.get('id')} does not trace to the selected candidate",
                )
            if not item.get("story_key"):
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} has no continuity story key"
                )
            if item.get("story_type") not in STORY_TYPES:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} has invalid story type"
                )
            claims = item.get("claims")
            if not isinstance(claims, list) or not claims:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} has no structured claims"
                )
            for claim in claims:
                if (
                    not isinstance(claim, dict)
                    or claim.get("classification")
                    not in {"FACT", "CLAIM", "DISPUTED", "UNKNOWN", "ESTIMATE"}
                    or not isinstance(claim.get("source_ids"), list)
                    or not set(claim["source_ids"]).issubset(sources)
                    or not claim.get("claim_type")
                ):
                    raise ProviderError(
                        "ARTICLE_SCHEMA_INVALID",
                        f"article {item.get('id')} has an invalid claim record",
                    )
            elements = item.get("editorial_elements")
            if not isinstance(elements, dict) or any(not elements.get(field) for field in required_elements):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} lacks required journalism elements")
            if section_id == "investigations":
                checks = item.get("investigation_checks")
                if (
                    not isinstance(checks, dict)
                    or any(
                        field not in checks
                        for field in (
                            "serious_accountability_claim", "counter_evidence_checked",
                            "response_status", "publication_ready",
                        )
                    )
                    or checks.get("response_status") not in {
                        "NOT_APPLICABLE", "SOUGHT", "RECEIVED", "DECLINED", "NO_RESPONSE"
                    }
                    or not isinstance(checks.get("serious_accountability_claim"), bool)
                    or not isinstance(checks.get("counter_evidence_checked"), bool)
                    or not isinstance(checks.get("publication_ready"), bool)
                    or not checks["publication_ready"]
                ):
                    raise ProviderError(
                        "ARTICLE_SCHEMA_INVALID",
                        "active investigation needs explicit passing fairness/readiness checks",
                    )
            word_count = len(re.findall(r"\S+", " ".join(item["body"])))
            if word_count < self.minimum_active_article_words:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID",
                    f"article {item.get('id')} has {word_count} words; hard minimum is {self.minimum_active_article_words}",
                )
            edition_words += word_count
            active_count += 1
        if seen != expected:
            missing = ",".join(sorted(expected - seen))
            raise ProviderError("ARTICLE_SCHEMA_INVALID", f"section decisions missing: {missing}")
        if active_count == 0 or edition_words < self.minimum_edition_words:
            raise ProviderError(
                "ARTICLE_SCHEMA_INVALID",
                f"edition has {active_count} active articles and {edition_words} words; minimum is {self.minimum_edition_words} words",
            )
        return value


def configured_byline(config: dict) -> str:
    publication = config.get("publication", {})
    template = publication.get("byline_template", "تحرير: {pen_name}")
    pen_name = publication.get("pen_name", "DRAGON")
    if not isinstance(template, str) or not isinstance(pen_name, str) or not pen_name.strip():
        raise ValueError("PUBLICATION_BYLINE_CONFIG_INVALID")
    fields = [
        (field, format_spec, conversion)
        for _literal, field, format_spec, conversion in Formatter().parse(template)
        if field is not None
    ]
    if fields != [("pen_name", "", None)] or any(character in template for character in "\r\n"):
        raise ValueError("PUBLICATION_BYLINE_CONFIG_INVALID")
    try:
        byline = template.format(pen_name=pen_name.strip())
    except (KeyError, ValueError) as exc:
        raise ValueError("PUBLICATION_BYLINE_CONFIG_INVALID") from exc
    if "{" in byline or "}" in byline or not byline.strip():
        raise ValueError("PUBLICATION_BYLINE_CONFIG_INVALID")
    return byline


def editorial_provider_from_config(config: dict, *, require_proven: bool = True):
    value = config.get("providers", {}).get("ai", {})
    if value.get("type") != "local-command":
        return UnconfiguredEditorialProvider()
    if require_proven and value.get("integration_test_status") != "PASS":
        return UnconfiguredEditorialProvider(reason="AI_PROVIDER_INTEGRATION_NOT_PROVEN")
    command = value.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        return UnconfiguredEditorialProvider(reason="AI_PROVIDER_CONFIGURATION_INCOMPLETE")
    command = [sys.executable if item == "{python}" else item for item in command]
    executable = command[0]
    if not Path(executable).is_file() and shutil.which(executable) is None:
        return UnconfiguredEditorialProvider(reason="AI_PROVIDER_EXECUTABLE_MISSING")
    return LocalCommandEditorialProvider(
        command=tuple(command),
        timeout_seconds=int(value.get("timeout_seconds", 7200)),
        minimum_active_article_words=int(value.get("minimum_active_article_words", 350)),
        minimum_edition_words=int(value.get("minimum_edition_words", 4000)),
        expected_byline=configured_byline(config),
    )
