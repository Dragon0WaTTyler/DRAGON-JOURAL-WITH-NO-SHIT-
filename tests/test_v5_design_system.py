from pathlib import Path

from dragon.design_system import (
    REQUIRED_COMPONENTS,
    REQUIRED_PAGE_GRAMMARS,
    compose_print_css,
    design_source_paths,
    load_arabic_design_fixture,
    validate_design_system,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design"


def test_modular_design_system_has_all_required_components_and_grammars() -> None:
    assert validate_design_system(DESIGN) == []
    css = compose_print_css(DESIGN)
    assert "design-system-sha256:" in css
    assert len(design_source_paths(DESIGN)) == 5
    assert all(f"component:{name}" in css for name in REQUIRED_COMPONENTS)
    assert all(f"grammar:{name}" in css for name in REQUIRED_PAGE_GRAMMARS)
    assert "direction: rtl" in css


def test_arabic_design_fixture_covers_mixed_direction_publication_cases() -> None:
    fixture = load_arabic_design_fixture(DESIGN)
    expected = {
        "long_headline", "short_headline", "punctuation", "numbers",
        "mixed_company", "mixed_url", "mixed_doi", "parentheses", "table",
        "chart_labels", "caption", "quotation", "multi_column_paragraph",
        "footnote", "epub_navigation",
    }
    assert expected <= fixture.keys()
    assert fixture["language"] == "ar" and fixture["direction"] == "rtl"
    assert any("\u0600" <= character <= "\u06ff" for character in fixture["long_headline"])
