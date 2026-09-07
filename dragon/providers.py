"""Editorial provider boundary for production and explicit fixture runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EditorialProvider(Protocol):
    mode: str

    def research(self, edition_date: str) -> dict: ...

    def articles(self, research: dict) -> list[dict]: ...


@dataclass(frozen=True)
class UnconfiguredEditorialProvider:
    mode: str = "production"

    def research(self, edition_date: str) -> dict:
        raise RuntimeError("AI_PROVIDER_UNCONFIGURED")

    def articles(self, research: dict) -> list[dict]:
        raise RuntimeError("AI_PROVIDER_UNCONFIGURED")


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

    def research(self, edition_date: str) -> dict:
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
