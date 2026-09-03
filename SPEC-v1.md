# DRAGON Daily Newspaper — Technical Specification v1

## Architecture

Daily production is coordinated by five ChatGPT Scheduled Work super-jobs over the authoritative 13 roles in `config/roles.yaml`. All scheduled stage semantics use `Africa/Casablanca`. `config/schedule.yaml` remains disabled and is not an activation mechanism for ChatGPT Scheduled Work.

The execution boundary is ChatGPT Plus only. The OpenAI API, `OPENAI_API_KEY`, pay-as-you-go usage, GitHub Actions as compute, paid external compute, self-hosted runners, and the user's PC as production runtime are forbidden.

## Tested Scheduled Work capabilities

Connected GitHub:
- TEXT READ: PASS
- UTF-8 TEXT WRITE: PASS
- TEXT READ-BACK: PASS
- BINARY IMAGE WRITE: UNSUPPORTED
- PDF BINARY WRITE: UNSUPPORTED
- EPUB BINARY WRITE: UNSUPPORTED

Scheduled repository executable runtime: `NOT_AVAILABLE`.

These are tested architecture facts. Do not model them as unknown capability probes.

## Scheduled stages

1. 07:45 Current News Desk
2. 08:00 Deep Features Desk
3. 08:50 Chief Editor
4. 09:25 Publication Builder
5. 09:55 Cover Director

Allowed stage values are `PENDING`, `RUNNING`, `COMPLETE`, `BLOCKED`, and `FAILED`.

### Chief Editor

Task 3 produces the canonical `edition.md`, `sources.json`, `manifest.json`, and editorial report. Editorial completion requires fact-check, citations, depth, Darija QA, GitHub text persistence/read-back, and exact Arabic-script count zero.

Before completion, scan the five Arabic Unicode ranges U+0600–U+06FF, U+0750–U+077F, U+08A0–U+08FF, U+FB50–U+FDFF, and U+FE70–U+FEFF. Locate every match, rewrite/transliterate naturally into Moroccan Darija Latin without changing facts, rescan, and repeat until zero. The same scheduled execution performs safe deterministic repair.

### Publication Builder

Task 4 is text-only. It creates semantic `edition.html`, `print.css`, XHTML-compatible `epub-content.xhtml`, and `publishing-report.json`. It validates UTF-8, mojibake, Arabic-script zero, source-link resolution, and connected GitHub text read-back.

`publishing=COMPLETE` means `publication_source_package=COMPLETE`, not binary publication complete. Required binary state:

- `pdf_binary=NOT_GENERATED_NO_RUNTIME`
- `epub_binary=NOT_GENERATED_NO_RUNTIME`
- `binary_artifacts=PENDING_MANUAL_CODEX_RENDER`
- `ready_for_codex_rendering=true`

A later manual Codex Cloud run may render and validate PDF/EPUB binaries from this package.

### Cover Director

Task 5 uses one lead, one cover mode, a compact persisted brief, and one simple 3:4 image-generation request. Visible text is limited to DRAGON masthead, date, main headline, and at most two teasers. Use one dominant concept and black/white/red hierarchy. No unrelated collage, fake documentary evidence, or Arabic script.

If generation fails, retry once only with an even simpler composition. `cover=COMPLETE` requires actual image generation PASS plus visual QA PASS. GitHub image archival is explicitly separate:

- `github_image_archive=UNSUPPORTED_BY_CONNECTOR`
- `cover_binary_archive=PENDING_MANUAL_ARCHIVE`

## Overall status

`overall_status` may be `COMPLETE` when all five scheduled stages are `COMPLETE`. Manual PDF/EPUB rendering and cover binary archival do not block scheduled overall completion, but their state fields must remain visible and truthful.

## Persistence semantics

Temporary/runtime existence is not persistence. A Scheduled Work text output is persisted only after connected GitHub write and exact canonical-path read-back. Binary persistence must never be inferred from text persistence.

## Editorial topology and depth

The role count remains exactly 13. Research desks return structured packets; Chief Editor synthesizes; fact-check and Darija QA are hard gates; Publishing role serves Task 4 and Task 5 without reducing the role registry.

Depth thresholds remain centralized in `config/editorial-depth.yaml`: edition 4000, History 800, Literature/Culture 800, Morocco 700, Palestine 500, Meknes 300 with explicit thin-news exception, and Science 500. Investigations may remain explicitly non-publication-ready.

## Binary handoff

Scheduled Work does not generate final PDF/EPUB binaries in this architecture. Manual Codex Cloud rendering is the supported later handoff. Cover binary archival also remains manual/supported-binary-persistence work.

Future maintainers must not reintroduce API, GitHub Actions compute, self-hosted runtime, or local-PC production dependencies to bypass this limitation.
