"""Deterministic Arabic, UTF-8, RTL, and mojibake quality gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import re
from typing import Iterable
from xml.etree import ElementTree


ARABIC_SCRIPT = re.compile(
    r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]"
)
ARABIC_LETTER = re.compile(
    r"[\u0621-\u063a\u0641-\u064a\u066e-\u066f\u0671-\u06d3\u06fa-\u06fc]"
)
LATIN_WORD = re.compile(r"(?<![\w@])(?:[A-Za-z][A-Za-z0-9.+#_-]{1,})(?![\w@])")
MOJIBAKE_MARKERS = (
    "\ufffd",
    "Ã",
    "Â",
    "Ø§",
    "Ø§Ù",
    "Ù„",
    "Ù…",
    "â€™",
    "â€œ",
    "â€",
)


@dataclass(frozen=True)
class LanguageQAResult:
    status: str
    checks: dict[str, str]
    metrics: dict[str, int | float]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class _RootHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root_attributes: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.root_attributes is None and tag.lower() == "html":
            self.root_attributes = {key.lower(): value or "" for key, value in attrs}


def decode_utf8(data: bytes) -> str:
    """Decode strict UTF-8 and reject a BOM or replacement character."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF8_BOM_NOT_ALLOWED")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("UTF8_INVALID") from exc
    if "\ufffd" in text:
        raise ValueError("UTF8_REPLACEMENT_CHARACTER")
    return text


def mojibake_occurrences(text: str) -> list[str]:
    return [marker for marker in MOJIBAKE_MARKERS if marker in text]


def _allowed_latin_words(values: Iterable[str]) -> set[str]:
    return {value.casefold() for value in values if value}


def validate_arabic_text(
    text: str,
    *,
    minimum_arabic_letters: int = 20,
    maximum_latin_word_ratio: float = 0.20,
    allowed_latin_terms: Iterable[str] = (),
) -> LanguageQAResult:
    """Validate Arabic-first reader text without treating Arabic as an error.

    The leakage gate is deliberately conservative: official technical names can
    be allowlisted, while a mostly Latin/transliterated edition cannot pass.
    """
    issues: list[str] = []
    arabic_letters = len(ARABIC_LETTER.findall(text))
    arabic_script = len(ARABIC_SCRIPT.findall(text))
    allowed = _allowed_latin_words(allowed_latin_terms)
    latin_words = [word for word in LATIN_WORD.findall(text) if word.casefold() not in allowed]
    lexical_total = arabic_letters + len(latin_words)
    latin_ratio = len(latin_words) / lexical_total if lexical_total else 1.0
    mojibake = mojibake_occurrences(text)

    if arabic_letters < minimum_arabic_letters:
        issues.append(
            f"ARABIC_LANGUAGE_INSUFFICIENT: {arabic_letters} Arabic letters; "
            f"minimum is {minimum_arabic_letters}"
        )
    if latin_ratio > maximum_latin_word_ratio:
        issues.append(
            "FOREIGN_LANGUAGE_LEAKAGE: "
            f"Latin-word ratio {latin_ratio:.3f} exceeds {maximum_latin_word_ratio:.3f}"
        )
    if mojibake:
        issues.append("MOJIBAKE_DETECTED: " + ", ".join(repr(item) for item in mojibake))

    checks = {
        "ARABIC_LANGUAGE": "PASS" if arabic_letters >= minimum_arabic_letters else "FAIL",
        "UTF8": "PASS" if "\ufffd" not in text else "FAIL",
        "MOJIBAKE": "PASS" if not mojibake else "FAIL",
        "FOREIGN_LANGUAGE_LEAKAGE": (
            "PASS" if latin_ratio <= maximum_latin_word_ratio else "FAIL"
        ),
    }
    return LanguageQAResult(
        status="PASS" if not issues else "FAIL",
        checks=checks,
        metrics={
            "arabic_script_characters": arabic_script,
            "arabic_letters": arabic_letters,
            "unapproved_latin_words": len(latin_words),
            "latin_word_ratio": round(latin_ratio, 6),
        },
        issues=tuple(issues),
    )


def validate_html_rtl(document: str) -> list[str]:
    parser = _RootHTMLParser()
    parser.feed(document)
    attrs = parser.root_attributes
    if attrs is None:
        return ["RTL_HTML_ROOT_MISSING"]
    issues: list[str] = []
    if attrs.get("lang", "").casefold() != "ar":
        issues.append("RTL_HTML_LANG_INVALID")
    if attrs.get("dir", "").casefold() != "rtl":
        issues.append("RTL_HTML_DIRECTION_INVALID")
    return issues


def validate_xhtml_rtl(document: str) -> list[str]:
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        return [f"XHTML_XML_INVALID: {exc}"]
    issues: list[str] = []
    language = root.get("lang") or root.get("{http://www.w3.org/XML/1998/namespace}lang")
    xml_language = root.get("{http://www.w3.org/XML/1998/namespace}lang")
    if language != "ar" or xml_language != "ar":
        issues.append("RTL_XHTML_LANGUAGE_INVALID")
    if root.get("dir", "").casefold() != "rtl":
        issues.append("RTL_XHTML_DIRECTION_INVALID")
    return issues
