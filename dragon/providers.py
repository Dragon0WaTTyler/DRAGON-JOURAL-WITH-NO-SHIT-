"""Editorial provider boundary for production and explicit fixture runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
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
        return {
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
                }
            ],
        }

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
    mode: str = "production"
    available: bool = True

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
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("AI_PROVIDER_RESPONSE_INVALID", "provider stdout is not one JSON value") from exc

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
        return value

    def articles(self, research: dict) -> list[dict]:
        value = self._invoke("articles", {"schema_version": 5, "research": research, "language": "ar"})
        if not isinstance(value, list):
            raise ProviderError("ARTICLE_SCHEMA_INVALID", "provider must return an article/skip list")
        expected = {section_id for section_id, _ in SECTION_HEADINGS}
        sources = {item["id"] for item in research["sources"]}
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
            if not set(item["source_ids"]).issubset(sources):
                raise ProviderError("ARTICLE_SCHEMA_INVALID", f"article {item.get('id')} cites unknown sources")
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
    executable = command[0]
    if not Path(executable).is_file() and shutil.which(executable) is None:
        return UnconfiguredEditorialProvider(reason="AI_PROVIDER_EXECUTABLE_MISSING")
    return LocalCommandEditorialProvider(
        tuple(command),
        int(value.get("timeout_seconds", 7200)),
        int(value.get("minimum_active_article_words", 350)),
        int(value.get("minimum_edition_words", 4000)),
    )
