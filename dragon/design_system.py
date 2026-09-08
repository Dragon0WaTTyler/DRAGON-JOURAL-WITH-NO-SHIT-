"""Validated, deterministic composition of DRAGON's modular print design system."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


DESIGN_BUNDLES = (
    "tokens/core.css",
    "typography/arabic.css",
    "components/newspaper.css",
    "pages/grammars.css",
    "cover/cover.css",
)

REQUIRED_TOKENS = {
    "--ink", "--paper", "--dragon-red", "--muted-rule", "--column-gutter",
}

REQUIRED_COMPONENTS = {
    "masthead", "section-bar", "headline", "kicker", "standfirst", "byline",
    "pull-quote", "sidebar", "timeline", "study-card", "evidence-box",
    "fact-check-verdict", "chart", "data-table", "document-excerpt",
    "brief-rail", "folio", "caption",
}

REQUIRED_PAGE_GRAMMARS = {
    "LEAD", "NORMAL_NEWS", "ANALYSIS", "INVESTIGATION_DOSSIER", "SCIENCE",
    "HISTORY", "CULTURE", "FACT_CHECK", "DATA", "DOCUMENT_PUBLIC_RECORD",
}


class DesignSystemError(RuntimeError):
    pass


def design_source_paths(design_root: Path) -> tuple[Path, ...]:
    return tuple(design_root / relative for relative in DESIGN_BUNDLES)


def _read_sources(design_root: Path) -> list[tuple[str, str]]:
    values = []
    for relative, path in zip(DESIGN_BUNDLES, design_source_paths(design_root)):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise DesignSystemError(f"DESIGN_SOURCE_INVALID:{relative}:{exc}") from exc
        if not text.strip():
            raise DesignSystemError(f"DESIGN_SOURCE_EMPTY:{relative}")
        values.append((relative, text))
    return values


def validate_design_system(design_root: Path) -> list[str]:
    try:
        sources = _read_sources(design_root)
    except DesignSystemError as exc:
        return [str(exc)]
    combined = "\n".join(text for _, text in sources)
    issues = []
    for token in sorted(REQUIRED_TOKENS):
        if f"{token}:" not in combined:
            issues.append(f"DESIGN_TOKEN_MISSING:{token}")
    for component in sorted(REQUIRED_COMPONENTS):
        if f"component:{component}" not in combined:
            issues.append(f"DESIGN_COMPONENT_MISSING:{component}")
    for grammar in sorted(REQUIRED_PAGE_GRAMMARS):
        if f'grammar:{grammar}' not in combined:
            issues.append(f"DESIGN_GRAMMAR_MISSING:{grammar}")
    if 'direction: rtl' not in combined or 'unicode-bidi: plaintext' not in combined:
        issues.append("DESIGN_RTL_CONTRACT_MISSING")
    return issues


def compose_print_css(design_root: Path) -> str:
    issues = validate_design_system(design_root)
    if issues:
        raise DesignSystemError("; ".join(issues))
    sources = _read_sources(design_root)
    digest = hashlib.sha256(
        "\n".join(f"{name}\0{text}" for name, text in sources).encode("utf-8")
    ).hexdigest()
    header = f"/* DRAGON design-system-sha256:{digest} */\n"
    return header + "\n".join(
        f"/* bundle:{name} */\n{text.rstrip()}\n" for name, text in sources
    )


def load_arabic_design_fixture(design_root: Path) -> dict:
    path = design_root / "fixtures" / "arabic-publication.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DesignSystemError(f"DESIGN_FIXTURE_INVALID:{exc}") from exc
    return value
