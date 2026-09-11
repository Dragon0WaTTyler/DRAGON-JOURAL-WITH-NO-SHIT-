"""Editorial provider boundary for production and explicit fixture runs."""

from __future__ import annotations

from collections import Counter
from math import ceil
from dataclasses import dataclass
from datetime import datetime, timezone
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
    def __init__(self, code: str, detail: str, *, diagnostics: dict | None = None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.diagnostics = diagnostics or {}


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

REPAIR_SKIP_REASON_CODES = {
    "EVIDENCE_RETRACTED",
    "CANDIDATE_REMOVED",
    "SOURCE_INVALIDATED",
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


def _valid_source_time(value: object, *, retrieval: bool = False) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return False
    return not retrieval or ("T" in candidate and parsed.tzinfo is not None)


def _stamp_retrieval_times(value: dict) -> dict:
    """The local provider, not the model, owns the evidence retrieval instant."""
    sources = value.get("sources")
    if not isinstance(sources, list):
        return value
    retrieved_at = datetime.now(timezone.utc).isoformat()
    normalized = dict(value)
    normalized["sources"] = [
        {**source, "accessed_at": retrieved_at} if isinstance(source, dict) else source
        for source in sources
    ]
    return normalized


def _synthetic_investigation_data() -> dict:
    return {
        "question": "كيف يختبر النظام حفظ ملف مساءلة اصطناعي من دون اتهام واقعي؟",
        "entities": [],
        "relationships": [],
        "contracts": [],
        "timeline": [],
        "archive_references": [],
        "leads": [],
        "material_uncertainties": [],
    }


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
                    "investigation_data": (
                        _synthetic_investigation_data()
                        if section_id == "investigations" else None
                    ),
                    "repair_skip_reason_code": None,
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


def _valid_investigation_data(value: object, source_ids: set[str]) -> bool:
    required = {
        "question", "entities", "relationships", "contracts", "timeline",
        "archive_references", "leads", "material_uncertainties",
    }
    if not isinstance(value, dict) or set(value) != required or not isinstance(value["question"], str):
        return False
    if not value["question"].strip() or not all(isinstance(value[field], list) for field in required - {"question"}):
        return False

    def exact(item: object, fields: set[str]) -> bool:
        return isinstance(item, dict) and set(item) == fields

    def valid_source_list(item: dict, *, nonempty: bool = False) -> bool:
        values = item.get("source_ids")
        return (
            isinstance(values, list)
            and (not nonempty or bool(values))
            and all(isinstance(source_id, str) for source_id in values)
            and set(values).issubset(source_ids)
        )

    entity_fields = {"entity_id", "entity_type", "name", "aliases", "confidence", "source_ids"}
    relation_fields = {"from_entity_id", "to_entity_id", "relationship_type", "source_ids", "confidence", "ambiguity"}
    contract_fields = {"contract_id", "buyer_entity_id", "supplier_entity_id", "amount", "currency", "award_date", "amendments", "execution_status", "source_ids"}
    timeline_fields = {"event_id", "date", "description", "source_ids"}
    archive_fields = {"source_id", "canonical_url", "retrieved_at", "sha256", "archive_locator"}
    lead_fields = {"description", "confidence", "source_ids", "not_proof_of_wrongdoing"}
    entities = value["entities"]
    entity_ids = {item.get("entity_id") for item in entities if isinstance(item, dict)}
    if len(entity_ids) != len(entities) or None in entity_ids:
        return False
    for item in entities:
        if (
            not exact(item, entity_fields)
            or item["entity_type"] not in {
                "Person", "Organization", "Company", "PublicBody", "Asset", "Address",
                "Identifier", "Contract", "Payment", "Ownership", "Directorship", "CourtCase",
            }
            or item["confidence"] not in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
            or not isinstance(item["aliases"], list)
            or not all(isinstance(alias, str) for alias in item["aliases"])
            or not valid_source_list(item)
        ):
            return False
    for item in value["relationships"]:
        if (
            not exact(item, relation_fields)
            or item["from_entity_id"] not in entity_ids
            or item["to_entity_id"] not in entity_ids
            or item["confidence"] not in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
            or not valid_source_list(item, nonempty=True)
        ):
            return False
    for item in value["contracts"]:
        if (
            not exact(item, contract_fields)
            or item["buyer_entity_id"] not in entity_ids
            or item["supplier_entity_id"] not in entity_ids
            or not isinstance(item["amount"], (int, float))
            or isinstance(item["amount"], bool)
            or not isinstance(item["amendments"], list)
            or not all(isinstance(amount, (int, float)) and not isinstance(amount, bool) for amount in item["amendments"])
            or not valid_source_list(item, nonempty=True)
        ):
            return False
    for item in value["timeline"]:
        if not exact(item, timeline_fields) or not valid_source_list(item, nonempty=True):
            return False
    for item in value["archive_references"]:
        if (
            not exact(item, archive_fields)
            or item["source_id"] not in source_ids
            or not _https_url(item["canonical_url"])
            or not isinstance(item["sha256"], str)
            or re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) is None
        ):
            return False
    for item in value["leads"]:
        if (
            not exact(item, lead_fields)
            or item["confidence"] not in {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
            or item["not_proof_of_wrongdoing"] is not True
            or not valid_source_list(item)
        ):
            return False
    return all(isinstance(item, str) for item in value["material_uncertainties"])


@dataclass(frozen=True)
class LocalCommandEditorialProvider:
    """JSON stdin/stdout adapter for an explicitly configured local runtime."""

    command: tuple[str, ...]
    timeout_seconds: int = 7200
    minimum_active_article_words: int = 350
    minimum_edition_words: int = 4000
    generation_target_edition_words: int = 6000
    generation_maximum_edition_words: int = 9000
    minimum_active_sections: int = 1
    coverage_requirements: tuple[tuple[str, tuple[str, ...], int], ...] = ()
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
            # Preserve the terminal diagnostic. A large generated prompt can
            # otherwise obscure the actual provider error (for example, an
            # authorization or quota condition) in the incident packet.
            detail = result.stderr.strip()[-2000:] or f"provider exited {result.returncode}"
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
        raw_value = self._invoke(
            "research",
            {
                "schema_version": 5,
                "edition_date": edition_date,
                "language": "ar",
                "continuity": continuity or {"edition_count": 0, "editions": []},
                "edition_readiness": self._edition_readiness_context(),
            },
        )
        value = _stamp_retrieval_times(raw_value) if isinstance(raw_value, dict) else raw_value
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
                or len(str(source.get("claim_supported") or "")) > 600
                or not _https_url(source.get("url"))
                or not _valid_source_time(source.get("publication_date"))
                or not _valid_source_time(source.get("accessed_at"), retrieval=True)
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
                    or any(
                        not isinstance(item, str) or len(item) > 600
                        for field in content_fields
                        for item in candidate[field]
                    )
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
                if section_status == "ACTIVE" and value.get("mode") != "synthetic" and (
                    not candidate["primary_evidence_source_ids"]
                    or not candidate["independent_evidence_source_ids"]
                ):
                    raise ProviderError(
                        "RESEARCH_PACKET_INVALID",
                        f"active candidate {candidate['id']} needs primary and independent evidence ids",
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
        self._ensure_research_sufficient_for_articles(research)
        budget_contract = self._article_budget_contract(research)
        payload = {
            "schema_version": 5,
            "research": research,
            "language": "ar",
            "quality_constraints": {
                "minimum_active_article_words": self.minimum_active_article_words,
                "minimum_edition_words": self.minimum_edition_words,
            },
            "article_budget_contract": budget_contract,
            "editorial_identity": {"expected_byline": self.expected_byline},
        }
        value = self._invoke("articles", payload)
        try:
            return self._validate_articles(value, research, budget_contract=budget_contract)
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
                        "validation_diagnostics": exc.diagnostics,
                        "failing_articles": exc.diagnostics.get("article_length_failures", []),
                        "aggregate": exc.diagnostics.get("aggregate", {}),
                        "previous_articles": value,
                        "instruction": (
                            "Preserve valid decision identity, evidence linkage, and factual claims; "
                            "repair every field needed to address the validation error and return "
                            "the complete articles wrapper. A zero-active or aggregate-word failure "
                            "is a collection-level defect, not a reason to preserve every skipped "
                            "decision verbatim."
                        ),
                    },
                },
            )
            return self._validate_articles(
                repaired, research, repair_from=value, budget_contract=budget_contract
            )

    def _article_budget_contract(self, research: dict) -> dict:
        """Create the one authoritative pre-provider word budget.

        The 6,000--9,000 generation range is the existing editorial-depth
        target.  It is deliberately above the 4,000 acceptance floor.  The
        target is divided across every research-selected article; no prompt
        gets to invent a different per-article target.
        """
        sections = research.get("sections") if isinstance(research, dict) else None
        sources = {
            item.get("id") for item in research.get("sources", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        synthetic = research.get("mode") == "synthetic"
        selected: list[tuple[dict, dict]] = []
        for section in sections or []:
            if not isinstance(section, dict) or section.get("status") != "ACTIVE":
                continue
            candidate = next(
                (
                    item for item in section.get("candidates", [])
                    if isinstance(item, dict) and item.get("id") == section.get("selected_candidate_id")
                ),
                None,
            )
            if candidate is None:
                raise ProviderError(
                    "RESEARCH_BUDGET_INSUFFICIENT",
                    f"selected section {section.get('section_id')} has no selected evidence packet",
                )
            selected.append((section, candidate))
        if not selected:
            raise ProviderError("RESEARCH_BUDGET_INSUFFICIENT", "no active sections have a word budget")
        target_total = max(self.minimum_edition_words, self.generation_target_edition_words)
        maximum_total = max(target_total, self.generation_maximum_edition_words)
        target_words = max(self.minimum_active_article_words, ceil(target_total / len(selected)))
        maximum_words = max(target_words, ceil(maximum_total / len(selected)))
        budgets = []
        infeasible = []
        for section, candidate in selected:
            evidence_ids = sorted(set().union(*(
                set(candidate.get(field, []))
                for field in (
                    "discovery_source_ids", "verification_source_ids",
                    "primary_evidence_source_ids", "independent_evidence_source_ids",
                )
            )))
            evidence_items = sum(
                len(candidate.get(field, []))
                for field in ("facts", "claims", "unknowns", "disputed_points")
            )
            primary_ids = set(candidate.get("primary_evidence_source_ids", []))
            independent_ids = set(candidate.get("independent_evidence_source_ids", []))
            if (
                not set(evidence_ids).issubset(sources)
                or not evidence_ids
                or (not synthetic and not primary_ids)
                or (not synthetic and not independent_ids)
                or (not synthetic and not primary_ids.issubset(sources))
                or (not synthetic and not independent_ids.issubset(sources))
                or evidence_items < 1
            ):
                infeasible.append({
                    "section_id": section.get("section_id"),
                    "candidate_id": candidate.get("id"),
                    "evidence_ids": evidence_ids,
                    "evidence_item_count": evidence_items,
                })
            section_id = str(section["section_id"])
            budgets.append({
                "article_id": candidate["id"],
                "section_id": section_id,
                "candidate_id": candidate["id"],
                "role": (
                    "LEAD" if section_id == "front" else
                    "INVESTIGATION" if section_id == "investigations" else "STANDARD"
                ),
                "minimum_words": self.minimum_active_article_words,
                "target_words": target_words,
                "maximum_words": maximum_words,
                "evidence_ids": evidence_ids,
                "evidence_item_count": evidence_items,
            })
        if infeasible:
            raise ProviderError(
                "RESEARCH_BUDGET_INSUFFICIENT",
                "research cannot safely support the planned article word budget",
                diagnostics={"infeasible_articles": infeasible},
            )
        return {
            "schema_version": 1,
            "acceptance_floor_words": self.minimum_edition_words,
            "generation_target_words": target_words * len(budgets),
            "generation_maximum_words": maximum_words * len(budgets),
            "articles": budgets,
        }

    def _edition_readiness_context(self) -> dict:
        return {
            "minimum_active_sections": self.minimum_active_sections,
            "coverage_rules": [
                {
                    "id": rule_id,
                    "sections": list(section_ids),
                    "minimum_active": minimum,
                }
                for rule_id, section_ids, minimum in self.coverage_requirements
            ],
            "minimum_edition_words": self.minimum_edition_words,
        }

    def _ensure_research_sufficient_for_articles(self, research: dict) -> None:
        """Block article generation when research has no publishable selection.

        ``NO_NEWS`` is valid per section, but an all-``NO_NEWS`` packet cannot
        satisfy the edition-wide active-article and word-count contract. Calling
        a live article provider in that state only wastes a bounded editorial
        attempt and can never create a supported article: the validator and
        prompt both prohibit activating a no-news section.
        """
        sources = research.get("sources") if isinstance(research, dict) else None
        sections = research.get("sections") if isinstance(research, dict) else None
        publishable_sections = {
            item.get("section_id")
            for item in sections or []
            if isinstance(item, dict)
            and item.get("selected_candidate_id")
            and isinstance(item.get("section_id"), str)
        }
        source_count = len(sources) if isinstance(sources, list) else 0
        section_count = len(sections) if isinstance(sections, list) else 0
        if len(publishable_sections) < self.minimum_active_sections:
            raise ProviderError(
                "RESEARCH_INSUFFICIENT",
                "research has "
                f"{len(publishable_sections)} selected section(s), but the inherited edition "
                f"architecture requires at least {self.minimum_active_sections} active sections "
                f"({source_count} sources, {section_count} section decisions); "
                "refusing an article-provider invocation that cannot meet the edition contract",
            )
        coverage_failures = []
        for rule_id, section_ids, minimum in self.coverage_requirements:
            actual = len(publishable_sections.intersection(section_ids))
            if actual < minimum:
                coverage_failures.append(f"{rule_id}:{actual}/{minimum}")
        if coverage_failures:
            raise ProviderError(
                "RESEARCH_INSUFFICIENT",
                "research does not meet inherited edition coverage "
                f"({source_count} sources, {section_count} section decisions); "
                f"missing={','.join(coverage_failures)}; "
                "refusing an article-provider invocation that cannot meet the edition contract",
            )
        sections_needed_for_word_floor = ceil(
            self.minimum_edition_words / self.minimum_active_article_words
        )
        if len(publishable_sections) < sections_needed_for_word_floor:
            raise ProviderError(
                "RESEARCH_INSUFFICIENT",
                "research has "
                f"{len(publishable_sections)} selected section(s), but at least "
                f"{sections_needed_for_word_floor} are required for the {self.minimum_edition_words}-word "
                f"edition floor when every active article must contain at least "
                f"{self.minimum_active_article_words} words; refusing an article-provider invocation "
                "that cannot meet the edition contract",
            )

    def _validate_articles(
        self, value: object, research: dict, *, repair_from: object | None = None,
        budget_contract: dict | None = None,
    ) -> list[dict]:
        if not isinstance(value, list):
            raise ProviderError("ARTICLE_SCHEMA_INVALID", "provider must return an article/skip list")
        expected = {section_id for section_id, _ in SECTION_HEADINGS}
        sources = {item["id"] for item in research["sources"]}
        research_sections = {
            item["section_id"]: item for item in research.get("sections", [])
        }
        previous_by_section = {
            item.get("section_id"): item
            for item in repair_from or []
            if isinstance(item, dict) and isinstance(item.get("section_id"), str)
        } if isinstance(repair_from, list) else {}
        budgets_by_section = {
            item.get("section_id"): item
            for item in (budget_contract or {}).get("articles", [])
            if isinstance(item, dict) and isinstance(item.get("section_id"), str)
        }
        seen = set()
        edition_words = 0
        active_count = 0
        length_failures: list[dict] = []
        selected_active_skipped: list[dict] = []
        repair_linkage_changes: list[dict] = []
        repair_shortened_articles: list[dict] = []
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
                previous = previous_by_section.get(section_id)
                selected = research_sections.get(section_id, {}).get("selected_candidate_id")
                if (
                    isinstance(previous, dict)
                    and previous.get("status") == "ACTIVE"
                    and previous.get("research_candidate_id") == selected
                    and item.get("repair_skip_reason_code") not in REPAIR_SKIP_REASON_CODES
                ):
                    raise ProviderError(
                        "ARTICLE_SCHEMA_INVALID",
                        f"repair changed selected active section {section_id} to SKIPPED without "
                        "an approved repair_skip_reason_code",
                    )
                if not isinstance(item.get("skip_reason"), str) or len(item["skip_reason"].strip()) < 10:
                    raise ProviderError("ARTICLE_SCHEMA_INVALID", f"section {section_id} needs a specific skip reason")
                if section_id in budgets_by_section:
                    selected_active_skipped.append({
                        "article_id": budgets_by_section[section_id]["article_id"],
                        "section_id": section_id,
                        "candidate_id": selected,
                        "target_words": budgets_by_section[section_id]["target_words"],
                        "evidence_ids": budgets_by_section[section_id]["evidence_ids"],
                    })
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
            previous = previous_by_section.get(section_id)
            if isinstance(previous, dict) and previous.get("status") == "ACTIVE":
                if (
                    previous.get("research_candidate_id") != item.get("research_candidate_id")
                    or previous.get("source_ids") != item.get("source_ids")
                ):
                    repair_linkage_changes.append({"article_id": item.get("id"), "section_id": section_id})
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
                investigation_data = item.get("investigation_data")
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
                    or not _valid_investigation_data(investigation_data, set(item["source_ids"]))
                ):
                    raise ProviderError(
                        "ARTICLE_SCHEMA_INVALID",
                        "active investigation needs explicit passing fairness/readiness checks",
                    )
            word_count = len(re.findall(r"\S+", " ".join(item["body"])))
            budget = budgets_by_section.get(section_id, {
                "target_words": self.minimum_active_article_words,
                "evidence_ids": item.get("source_ids", []),
            })
            if word_count < self.minimum_active_article_words:
                length_failures.append({
                    "article_id": item.get("id"), "section_id": section_id,
                    "actual_words": word_count,
                    "minimum_words": self.minimum_active_article_words,
                    "target_words": budget["target_words"],
                    "deficit_to_minimum": self.minimum_active_article_words - word_count,
                    "deficit_to_target": max(0, budget["target_words"] - word_count),
                    "evidence_ids": budget["evidence_ids"],
                })
            if isinstance(previous, dict) and previous.get("status") == "ACTIVE":
                previous_words = len(re.findall(r"\S+", " ".join(previous.get("body", []))))
                if word_count < previous_words:
                    repair_shortened_articles.append({
                        "article_id": item.get("id"), "section_id": section_id,
                        "previous_words": previous_words, "actual_words": word_count,
                    })
            edition_words += word_count
            active_count += 1
        if seen != expected:
            missing = ",".join(sorted(expected - seen))
            raise ProviderError("ARTICLE_SCHEMA_INVALID", f"section decisions missing: {missing}")
        aggregate = {
            "active_articles": active_count,
            "raw_active_words": edition_words,
            "valid_active_words": edition_words if not length_failures else 0,
            "minimum_words": self.minimum_edition_words,
            "target_words": (budget_contract or {}).get("generation_target_words", self.minimum_edition_words),
            "deficit_to_minimum": max(0, self.minimum_edition_words - edition_words),
            "deficit_to_target": max(0, (budget_contract or {}).get("generation_target_words", self.minimum_edition_words) - edition_words),
        }
        if length_failures or selected_active_skipped or repair_linkage_changes or repair_shortened_articles or active_count == 0 or edition_words < self.minimum_edition_words:
            diagnostics = {
                "article_length_failures": length_failures,
                "selected_active_skipped": selected_active_skipped,
                "repair_linkage_changes": repair_linkage_changes,
                "repair_shortened_articles": repair_shortened_articles,
                "aggregate": aggregate,
            }
            fragments = [
                f"{item['article_id']}={item['actual_words']}/{item['minimum_words']}"
                for item in length_failures
            ]
            if selected_active_skipped:
                fragments.append("selected_active_skipped=" + ",".join(item["section_id"] for item in selected_active_skipped))
            if repair_linkage_changes:
                fragments.append("repair_linkage_changed=" + ",".join(item["section_id"] for item in repair_linkage_changes))
            if repair_shortened_articles:
                fragments.append("repair_shortened=" + ",".join(item["section_id"] for item in repair_shortened_articles))
            fragments.append(f"aggregate={edition_words}/{self.minimum_edition_words}")
            raise ProviderError(
                "ARTICLE_SCHEMA_INVALID",
                "article budget validation failed: " + "; ".join(fragments),
                diagnostics=diagnostics,
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
    readiness = config.get("editorial_readiness", {})
    word_budget = config.get("editorial_word_budget", {})
    coverage = readiness.get("coverage_rules", []) if isinstance(readiness, dict) else []
    try:
        coverage_requirements = tuple(
            (
                str(rule["id"]),
                tuple(str(section) for section in rule["sections"]),
                int(rule["minimum_active"]),
            )
            for rule in coverage
        )
        minimum_active_sections = int(readiness.get("minimum_active_sections", 1))
    except (KeyError, TypeError, ValueError) as exc:
        return UnconfiguredEditorialProvider(reason="EDITORIAL_READINESS_CONFIG_INVALID")
    if minimum_active_sections < 1 or any(
        not rule_id or not section_ids or minimum < 1
        for rule_id, section_ids, minimum in coverage_requirements
    ):
        return UnconfiguredEditorialProvider(reason="EDITORIAL_READINESS_CONFIG_INVALID")
    try:
        minimum_edition_words = int(value.get("minimum_edition_words", 4000))
        target_edition_words = int(word_budget.get("generation_target_edition_words", 6000))
        maximum_edition_words = int(word_budget.get("generation_maximum_edition_words", 9000))
    except (TypeError, ValueError):
        return UnconfiguredEditorialProvider(reason="EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
    if (
        target_edition_words < minimum_edition_words
        or maximum_edition_words < target_edition_words
        or int(word_budget.get("acceptance_floor_words", minimum_edition_words))
        != minimum_edition_words
    ):
        return UnconfiguredEditorialProvider(reason="EDITORIAL_WORD_BUDGET_CONFIG_INVALID")
    return LocalCommandEditorialProvider(
        command=tuple(command),
        timeout_seconds=int(value.get("timeout_seconds", 7200)),
        minimum_active_article_words=int(value.get("minimum_active_article_words", 350)),
        minimum_edition_words=minimum_edition_words,
        generation_target_edition_words=target_edition_words,
        generation_maximum_edition_words=maximum_edition_words,
        minimum_active_sections=minimum_active_sections,
        coverage_requirements=coverage_requirements,
        expected_byline=configured_byline(config),
    )
