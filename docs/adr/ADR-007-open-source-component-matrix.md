# ADR-007: open-source component decision matrix

- Status: accepted for migration; deferred entries require a new ADR before adoption
- Date: 2026-09-08
- Classes: `DIRECT`, `OPTIONAL`, `BORROW ARCHITECTURE`, `BENCHMARK`, `REJECT`

## Decision rules

DRAGON prefers its working local code when a dependency would add a daemon,
second scheduler, paid/keyed service, weak Arabic behavior, unclear provenance,
or disproportionate operational weight. `OPTIONAL` and `BENCHMARK` are not
installed or available capabilities. Before later adoption, a component must
receive a current license/maintenance review, an Arabic fixture where relevant,
bounded failure behavior, and a provider integration test.

## Strong/direct candidate list

| Project | Class | Decision and failure posture |
| --- | --- | --- |
| `advaitpaliwal/feynman` | BORROW ARCHITECTURE | Borrow iterative research decomposition; do not add another agent runtime without a fixed benchmark advantage. |
| `adbar/trafilatura` | DIRECT | Normal bounded HTML extraction. DRAGON owns HTTPS/size checks and treats output as extracted, not verified. |
| `unclecode/crawl4ai` | OPTIONAL | Exceptional JS-heavy fallback only after browser sandbox, resource limits, and failure fixtures pass. |
| `alephdata/followthemoney` | OPTIONAL | Useful entity/document model for mature investigations; current dossiers do not justify its footprint yet. |
| `opensanctions/opensanctions` | OPTIONAL | Provider for relevant sanctions/entity questions, subject to dataset license, freshness, and exact-record provenance review. |
| `DIYgod/RSSHub` | OPTIONAL | Disabled discovery adapter; no dependency on an unproved public instance or new self-hosted daemon. |
| `dgtlmoon/changedetection.io` | BORROW ARCHITECTURE | Borrow page-change/watchlist semantics; prefer a smaller Git-backed watcher until a daemon is justified. |
| `jgm/pandoc` | BENCHMARK | Compare only for EPUB/source conversion; keep the passing native EPUB builder unless it wins Arabic/lineage fixtures. |
| `w3c/epubcheck` | DIRECT | Pinned 5.3.0 hard validator; full JSON, version, and JAR hash are persisted. |
| `vercel/satori` | BENCHMARK | No adoption until Arabic shaping, bidi, line-breaking, and deterministic cover fixtures pass. |
| `linebender/resvg` | BENCHMARK | Candidate deterministic SVG rasterizer only if an SVG cover path is accepted and Arabic remains correct. |
| `lovell/sharp` | OPTIONAL | Candidate image treatment/crop/composite tool; Pillow already satisfies current local needs. |
| `vega/vega-lite` | OPTIONAL | Adopt per chart when source IDs, units, period, axes, and Arabic labels are data-bound; never invent chart data. |
| `Future-House/paper-qa` | OPTIONAL | Consider for authorized large scientific corpora only after local/API footprint and evidence-locator fidelity tests. |

## Optional/on-demand list

| Project | Class | Decision and failure posture |
| --- | --- | --- |
| `ICIJ/datashare` | OPTIONAL | Large-corpus investigation engine only for an authorized corpus; never a daily dependency. |
| `open-contracting/kingfisher-process` | OPTIONAL | Procurement normalization when OCP data is actually in scope; keep outside the ordinary news path. |
| `bellingcat/auto-archiver-setup-tool` | OPTIONAL | Authorized evidence capture only after rights, storage, and executable-download controls are approved. |
| `ArchiveBox/ArchiveBox` | OPTIONAL | On-demand archive provider; outage must not block unrelated daily sections. |
| `gotenberg/gotenberg` | BENCHMARK | Container/server PDF fallback only if it beats the protected local renderer and does not become a second control plane. |
| `wwebjs/whatsapp-web.js` | REJECT | Browser-session automation is less appropriate than the explicit Meta provider and complicates credentials/idempotency. |
| `mediacloud/api-client` | OPTIONAL | Discovery/coverage research only with credentials and clear API terms; not verification. |
| `JBGruber/LexisNexisTools` | OPTIONAL | Only for authorized Nexis exports; never add R or imply database access without such files. |
| `fhamborg/news-please` | BENCHMARK | Extraction comparison fixture only; avoid two permanent ordinary-HTML extractors without a failover win. |
| `public-accountability/littlesis-rails` | OPTIONAL | Entity-relationship research for a justified investigation; not a daily daemon. |

## Architecture/methodology list

| Project | Class | Decision and failure posture |
| --- | --- | --- |
| `falense/openpaper` | BORROW ARCHITECTURE | Selectively adapt listing-before-content ingestion, source-adapter boundaries, preference-aware curation feedback, and slot-based broadsheet presentation. Do not install it as a core DRAGON runtime or adopt its Claude Code, Playwright, scheduler, state, or publishing control plane. |
| `meedan/alegre` | BORROW ARCHITECTURE | Stable multilingual event similarity/clustering concepts; current deterministic clustering remains primary. |
| `kartikeyaagr/Media-Bias-Analysis` | BORROW ARCHITECTURE | Coverage-comparison methodology only; DRAGON does not infer hidden motives. |
| `meedan/check` | BORROW ARCHITECTURE | Claim/evidence workflow concepts; no second case-management service. |
| `bellingcat/open-source-research-notebooks` | BORROW ARCHITECTURE | Reproducible research notebook practices and locator discipline. |
| `Imbad0202/academic-research-skills-codex` | BORROW ARCHITECTURE | Research question and evidence-reading patterns; no copied runtime assumption. |
| `Imbad0202/critical-thinking-for-humans` | BORROW ARCHITECTURE | Counter-position, alternative explanation, and uncertainty prompts. |
| `Imbad0202/autoresearch` | BORROW ARCHITECTURE | Candidate/evaluate/promote-or-reject loop; production never rewrites itself nightly. |
| `Imbad0202/cc-user-autopsy` | BORROW ARCHITECTURE | Metric-driven self-audit and user-feedback queue. |
| `Imbad0202/huashu-md-html` | BORROW ARCHITECTURE | Publication-source transformation ideas only; canonical Arabic lineage remains local. |
| `Imbad0202/tw-formal-writing` | BORROW ARCHITECTURE | Formal-language consistency concepts, adapted for Arabic rather than copied. |
| `Imbad0202/automated-w2s-research` | BORROW ARCHITECTURE | Generator/judge isolation principle. |
| `florianbuetow/agentic-news-generator` | BORROW ARCHITECTURE | News pipeline role separation; no reliance on its scheduler or product assumptions. |
| `stanford-oval/storm` | BORROW ARCHITECTURE | Perspective/question-tree and synthesis concepts; no extra service. |
| `SkyworkAI/DeepResearchAgent` | BORROW ARCHITECTURE | Evolution control-plane sequence and evaluator separation. |
| `Ayanami0730/deep_research_bench` / DeepResearch Bench II | BORROW ARCHITECTURE | Fixed multi-dimensional research evaluation concepts. |
| `Alibaba-NLP/DeepResearch` | BORROW ARCHITECTURE | Research planning/evidence workflow ideas only. |
| `assafelovic/gpt-researcher` | BORROW ARCHITECTURE | Source breadth and report pipeline concepts; no runtime adoption. |
| `AkariAsai/OpenScholar` | BORROW ARCHITECTURE | Scholarly retrieval/citation evaluation concepts. |
| `docxology/template_newspaper` | BORROW ARCHITECTURE | Fixed page furniture plus flowed body columns. |
| `electricbookworks/paged-design` | BORROW ARCHITECTURE | Modular print tokens/components/pages. |
| `fpound/quired` | BORROW ARCHITECTURE | Render-detect-repair-compare Layout Doctor algorithm. |

## Renderer/orchestrator decisions

| Project | Class | Decision and failure posture |
| --- | --- | --- |
| `pagedjs/pagedjs` | BENCHMARK | Identical Arabic fixture benchmark before any renderer change. |
| `pagedjs/pagedjs-cli` | BENCHMARK | Same benchmark; no permanent parallel renderer without explicit primary/fallback policy. |
| `typst/typst` | BENCHMARK | Compare Arabic shaping, columns, links, determinism, and local/GitHub fit. |
| `vivliostyle/vivliostyle-cli` | OPTIONAL | Evaluate later only if existing benchmarks expose an unresolved publishing gap. |
| `PrefectHQ/prefect` | REJECT | Current orchestrator already provides checkpoints/recovery; Prefect risks a second scheduler/control plane. |

## Explicit rejects/catalog-only items

| Project | Class | Decision and failure posture |
| --- | --- | --- |
| `FreshRSS/FreshRSS` | REJECT | Adds a feed-server/dashboard product DRAGON does not need. |
| `RSSNext/Folo` | REJECT | Reader/dashboard product, not a bounded newsroom adapter. |
| `alephdata/aleph` legacy | REJECT | Legacy/heavy platform; use narrower entity methods/providers if needed. |
| `yihui/litedown` | REJECT | No material advantage to the current Arabic HTML/EPUB path. |
| `Sci-Hub` | REJECT | Unauthorized access route; never use. |
| `lazyoffice-opneclwd` | REJECT | Unclear fit/trust; do not execute or depend on it. |
| `claw-code` | REJECT | Unclear fit/trust; do not execute or depend on it. |
| `30days-challange` | REJECT | No production relevance. |
| standalone `experiment-agent` | REJECT | Evolution methodology is already absorbed without another agent runtime. |
| `public-apis/public-apis` | BORROW ARCHITECTURE | Catalog/discovery hints only; each actual provider needs its own ADR and proof. |
| `LexisNexisTools` without authorized exports | REJECT | Never imply access or add an R dependency without authorized input files. |

## Primary references for adopted components

- Trafilatura usage/API: <https://trafilatura.readthedocs.io/en/latest/usage-python.html>
- EPUBCheck project/release: <https://github.com/w3c/epubcheck>
- EPUBCheck CLI/JSON output: <https://w3c.github.io/epubcheck/docs/cli/>
- OpenPaper architecture and license: <https://github.com/falense/openpaper>
- OpenPaper fetcher contract: <https://github.com/falense/openpaper/blob/main/skills/openpaper/references/fetcher-guide.md>

No deferred entry is a production capability. Its failure mode today is simply
`NOT_CONFIGURED` or `NOT_PROVEN`, and the current working pipeline continues.
