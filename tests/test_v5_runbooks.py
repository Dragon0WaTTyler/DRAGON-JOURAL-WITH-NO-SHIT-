from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "scheduler-failure.md", "source-discovery-failure.md", "source-fetch-failure.md",
    "extraction-failure.md", "document-parse-failure.md", "clustering-failure.md",
    "research-failure.md", "provenance-failure.md", "editorial-failure.md",
    "arabic-qa-failure.md", "investigation-failure.md", "cover-failure.md",
    "layout-failure.md", "pdf-failure.md", "epub-failure.md", "git-conflict.md",
    "remote-readback-failure.md", "delivery-failure.md",
}
HEADINGS = {
    "## Symptoms", "## Failure codes", "## Likely causes", "## Automatic actions",
    "## Fallback order", "## Data never to overwrite", "## Retry limit",
    "## Stop condition", "## Resume behavior", "## Manual recovery",
}


def test_required_failure_runbooks_are_complete() -> None:
    directory = ROOT / "runbooks"
    assert {path.name for path in directory.glob("*.md")} == FILES
    for name in FILES:
        text = (directory / name).read_text(encoding="utf-8")
        assert all(heading in text for heading in HEADINGS), name
        assert "never" in text.casefold(), name
