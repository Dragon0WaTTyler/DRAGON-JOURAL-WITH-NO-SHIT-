"""Editorial provider boundary for production and explicit fixture runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
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


@dataclass(frozen=True)
class SyntheticEditorialProvider:
    """Deterministic, clearly labelled fixture data; never a news source."""

    mode: str = "synthetic"
    available: bool = True

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
                    "candidates": candidates,
                    "selected_candidate_id": candidates[0]["id"],
                    "selection_reason": "اختيار ثابت لاختبار خط الإنتاج فقط",
                }
            )
        return packet

    def articles(self, research: dict) -> list[dict]:
        date_value = research["edition_date"]
        articles: list[dict] = []
        for index, (section_id, heading) in enumerate(SECTION_HEADINGS, start=1):
            articles.append(
                {
                    "id": f"fixture-{index:02d}",
                    "section_id": section_id,
                    "section": heading,
                    "status": "ACTIVE",
                    "headline": f"مادة اختبارية لقسم {heading}",
                    "standfirst": "نص اصطناعي ثابت للتحقق من سير التحرير والطباعة، ولا يمثل خبرا حقيقيا.",
                    "byline": "تحرير: \u200eDRAGON\u200e",
                    "body": [
                        "هذه فقرة عربية مصطنعة صممت لاختبار سلامة الترميز واتجاه القراءة وتسلسل الصفحات. لا تتضمن الفقرة ادعاء واقعيا، ولا يجوز تقديمها إلى القارئ بوصفها تغطية صحفية.",
                        f"يسجل هذا النموذج تاريخ النسخة \u200e{date_value}\u200e ويختبر وجود عنوان القسم والمتن والمصدر وحالة المادة. الغرض تقني بحت، وتبقى مرحلة الإنتاج الحقيقي متوقفة إلى حين تهيئة مزود تحريري موثوق.",
                        "تتحقق بوابة الجودة من العربية السليمة، ومن غياب أحرف الترميز التالفة، ومن اتصال كل مادة بمصدر ظاهر. كما تحفظ النتائج في ملفات قابلة للتدقيق والاستئناف.",
                    ],
                    "source_ids": ["fixture-source"],
                    "research_candidate_id": f"{section_id}-candidate-1",
                    "story_key": f"synthetic-{section_id}-{date_value}",
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
                    "fixture": True,
                }
            )
        return articles


def _https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.path not in {"", "/"}


@dataclass(frozen=True)
class LocalCommandEditorialProvider:
    """JSON stdin/stdout adapter for an explicitly configured local runtime."""

    command: tuple[str, ...]
    timeout_seconds: int = 7200
    minimum_active_article_words: int = 350
    minimum_edition_words: int = 4000
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
        )
        for source in sources:
            if (
                not isinstance(source, dict)
                or any(not source.get(field) for field in required_source_fields)
                or not isinstance(source.get("id"), str)
                or not _https_url(source.get("url"))
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
            candidates = section.get("candidates")
            if not isinstance(candidates, list) or len(candidates) < 2:
                raise ProviderError(
                    "RESEARCH_PACKET_INVALID",
                    f"section {section.get('section_id')} needs at least two ranked candidates",
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
            if selected not in candidate_ids or not section.get("selection_reason"):
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
            required = ("id", "section", "headline", "standfirst", "byline", "body", "source_ids")
            if status != "ACTIVE" or any(not item.get(field) for field in required):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"active section {section_id} is incomplete")
            if not isinstance(item["body"], list) or not all(isinstance(paragraph, str) for paragraph in item["body"]):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} body is invalid")
            if not isinstance(item["source_ids"], list) or not set(item["source_ids"]).issubset(sources):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} cites unknown sources")
            selected = research_sections.get(section_id, {}).get("selected_candidate_id")
            if item.get("research_candidate_id") != selected:
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID",
                    f"article {item.get('id')} does not trace to the selected candidate",
                )
            if not item.get("story_key"):
                raise ProviderError(
                    "ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} has no continuity story key"
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
        tuple(command),
        int(value.get("timeout_seconds", 7200)),
        int(value.get("minimum_active_article_words", 350)),
        int(value.get("minimum_edition_words", 4000)),
    )
