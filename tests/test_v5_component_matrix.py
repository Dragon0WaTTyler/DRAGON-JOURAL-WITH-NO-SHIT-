from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "advaitpaliwal/feynman", "adbar/trafilatura", "unclecode/crawl4ai",
    "alephdata/followthemoney", "opensanctions/opensanctions", "DIYgod/RSSHub",
    "dgtlmoon/changedetection.io", "jgm/pandoc", "w3c/epubcheck",
    "vercel/satori", "linebender/resvg", "lovell/sharp", "vega/vega-lite",
    "Future-House/paper-qa", "ICIJ/datashare", "open-contracting/kingfisher-process",
    "bellingcat/auto-archiver-setup-tool", "ArchiveBox/ArchiveBox",
    "gotenberg/gotenberg", "wwebjs/whatsapp-web.js", "mediacloud/api-client",
    "JBGruber/LexisNexisTools", "fhamborg/news-please",
    "public-accountability/littlesis-rails", "meedan/alegre",
    "kartikeyaagr/Media-Bias-Analysis", "meedan/check",
    "bellingcat/open-source-research-notebooks", "Imbad0202/academic-research-skills-codex",
    "Imbad0202/critical-thinking-for-humans", "Imbad0202/autoresearch",
    "Imbad0202/cc-user-autopsy", "Imbad0202/huashu-md-html",
    "Imbad0202/tw-formal-writing", "Imbad0202/automated-w2s-research",
    "florianbuetow/agentic-news-generator", "stanford-oval/storm",
    "SkyworkAI/DeepResearchAgent", "Ayanami0730/deep_research_bench",
    "Alibaba-NLP/DeepResearch", "assafelovic/gpt-researcher", "AkariAsai/OpenScholar",
    "docxology/template_newspaper", "electricbookworks/paged-design", "fpound/quired",
    "pagedjs/pagedjs", "pagedjs/pagedjs-cli", "typst/typst",
    "vivliostyle/vivliostyle-cli", "PrefectHQ/prefect", "FreshRSS/FreshRSS",
    "RSSNext/Folo", "alephdata/aleph", "yihui/litedown", "Sci-Hub",
    "lazyoffice-opneclwd", "claw-code", "30days-challange", "experiment-agent",
    "public-apis/public-apis",
    "falense/openpaper",
}


def test_component_matrix_classifies_every_required_project() -> None:
    text = (ROOT / "docs" / "adr" / "ADR-007-open-source-component-matrix.md").read_text(encoding="utf-8")
    assert all(name in text for name in REQUIRED)
    assert "DIRECT" in text
    assert "OPTIONAL" in text
    assert "BORROW ARCHITECTURE" in text
    assert "BENCHMARK" in text
    assert "REJECT" in text
    assert "second scheduler" in text
    assert "Do not install it as a core DRAGON runtime" in text
