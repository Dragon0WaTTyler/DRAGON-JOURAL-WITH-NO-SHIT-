# ADR-008: selectively adapt the OpenPaper reference architecture

- Status: accepted as a reference; no runtime adoption
- Date: 2026-09-08
- Upstream: `falense/openpaper`
- Decision: `BORROW / SELECTIVELY ADAPT`

## Context

OpenPaper is an MIT-licensed Claude Code plugin for a personalized daily HTML
newspaper. Its documented pipeline has three boundaries: ingest, curate, and
present. Ingestion first gathers listings, centrally deduplicates them, and only
then retrieves full content. Source-specific standalone fetchers share a common
contract; curation uses an evolving reader preference file; presentation assigns
selected articles to slots in a responsive Jinja2 broadsheet.

Those boundaries are useful design evidence for DRAGON, but the upstream product
has different operational assumptions. It relies on Claude Code, generates
per-source Python scripts, can use Playwright and `uv`, stores its own working
state, and targets a single-reader HTML edition. Installing it would introduce a
parallel agent/runtime and publication path instead of strengthening DRAGON's
existing audited pipeline.

## Decision

DRAGON will borrow four architectural ideas:

1. Separate low-cost discovery/listing from bounded full-text extraction, and
   deduplicate before expensive retrieval.
2. Keep source adapters behind a small, machine-testable contract with explicit
   partial-failure reporting.
3. Treat preference feedback as versioned editorial input, never as an
   engagement-optimization objective or an unattended production rewrite.
4. Assign approved stories to semantic layout slots before rendering, while
   keeping body flow distinct from fixed page furniture.

DRAGON will not install OpenPaper as a core runtime, vendor its plugin, execute
generated fetchers, adopt its Playwright/browser lifecycle, or use its state,
scheduler, curation agent, templates, or publishing output as production truth.
Its HTML design is a visual/architectural reference, not an Arabic typography
oracle.

## DRAGON ownership boundaries

| Concern | DRAGON remains authoritative |
| --- | --- |
| Source admission | Provider registry, legality, provenance, bounded networking, and truthful capability states |
| Extraction | Existing HTTPS controls and Trafilatura path; extraction never implies verification |
| Deduplication | Layered URL, normalized-content, token/edit, wire, and origin-aware identity |
| Curation | Arabic editorial policy, claim graph, evidence passports, uncertainty, and human approval |
| Layout | DRAGON cover modes, Arabic shaping/bidi, page plans, Layout Doctor, PDF and EPUB gates |
| Operations | One Codex local scheduler, checkpoint/retry state, receipts, Git archive/readback, and delivery |

No OpenPaper process is started when it is absent or fails. The production
failure posture is therefore `NOT_INSTALLED_REFERENCE_ONLY`, and DRAGON continues
with its existing components.

## Evidence reviewed

- Repository README and architecture: <https://github.com/falense/openpaper>
- Fetcher interface and listing/content boundary: <https://github.com/falense/openpaper/blob/main/skills/openpaper/references/fetcher-guide.md>
- MIT license: <https://github.com/falense/openpaper/blob/main/LICENSE>
