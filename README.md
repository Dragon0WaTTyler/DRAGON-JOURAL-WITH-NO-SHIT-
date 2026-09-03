# DRAGON Daily Newspaper

DRAGON is a five-super-job ChatGPT Scheduled Work production system over 13 editorial roles. GitHub is the permanent source of truth for editorial memory, research handoffs, canonical edition text, publication-source text, reports, and workflow state.

## Tested production architecture

Real end-to-end testing established the following:

- Current News Desk: live research + GitHub text read/write/read-back PASS.
- Deep Features Desk: deep research + GitHub text write/read-back PASS.
- Chief Editor: full edition, fact-check, depth gates, persistence PASS; an initial edition contained 25 Arabic-script glyphs, so deterministic scan/repair/rescan to zero is now a permanent hard gate.
- Publication Builder: semantic HTML, print CSS, EPUB XHTML source, and publishing report PASS as text.
- Cover Director: compact brief-first image generation PASS. A large all-in-one image prompt failed; the permanent contract therefore keeps the rendering request deliberately simple with one retry maximum.

Scheduled Work does **not** expose executable repository runtime in the tested workflow. The connected GitHub path supports UTF-8 text but not image, PDF, or EPUB binary writes. This is a tested architecture limitation, not an unknown.

## Five scheduled super-jobs

All use `Africa/Casablanca`:

1. 07:45 — Current News Desk
2. 08:00 — Deep Features Desk
3. 08:50 — Chief Editor
4. 09:25 — Publication Builder
5. 09:55 — Cover Director

The 13 underlying roles in `config/roles.yaml` remain unchanged. `config/schedule.yaml` remains disabled; this repository does not create or enable schedules.

## Task 4: publication source, not binaries

Scheduled Task 4 creates:

```text
editions/YYYY/MM/YYYY-MM-DD/edition.html
editions/YYYY/MM/YYYY-MM-DD/print.css
editions/YYYY/MM/YYYY-MM-DD/epub-content.xhtml
daily-runs/YYYY-MM-DD/publishing-report.json
```

`publishing=COMPLETE` means **PUBLICATION SOURCE PACKAGE COMPLETE**. It must also expose:

```text
pdf_binary = NOT_GENERATED_NO_RUNTIME
epub_binary = NOT_GENERATED_NO_RUNTIME
binary_artifacts = PENDING_MANUAL_CODEX_RENDER
ready_for_codex_rendering = true
```

PDF and EPUB binaries are rendered later in a manual Codex Cloud run from the persisted source package.

## Task 5: compact cover flow

The Cover Director reads the final edition, editorial report, and `design/DRAGON-COVER-STYLE.md`; selects one lead and one mode; persists `cover-brief.json`; generates one actual 3:4 cover with minimal text and at most two teasers; runs visual QA; and retries once only with a simpler composition if needed.

`cover=COMPLETE` requires image generation PASS and visual QA PASS. It does not require GitHub image archival:

```text
github_image_archive = UNSUPPORTED_BY_CONNECTOR
cover_binary_archive = PENDING_MANUAL_ARCHIVE
```

## Arabic-script hard gate

Task 3 scans U+0600–U+06FF, U+0750–U+077F, U+08A0–U+08FF, U+FB50–U+FDFF, and U+FE70–U+FEFF. Every occurrence is repaired/transliterated into natural Moroccan Darija Latin and the whole edition is rescanned until the exact count is zero.

## Execution boundary

Allowed: ChatGPT Plus Scheduled Work and connected GitHub text persistence. Forbidden: OpenAI API, `OPENAI_API_KEY`, pay-as-you-go, GitHub Actions as external compute, paid external compute, self-hosted runners, and the user's PC as production runtime.

Manual Codex Cloud rendering may be used later for binary PDF/EPUB artifacts. Do not schedule Codex Cloud unless a native supported scheduling mechanism exists in the future.

See `AGENTS.md`, `SPEC-v1.md`, `config/scheduled-workflow.yaml`, and `config/execution-constraints.yaml`.
