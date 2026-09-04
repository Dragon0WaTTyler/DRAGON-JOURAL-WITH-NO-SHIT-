# DRAGON Daily Newspaper — Production operating contract

This repository is the source of truth for DRAGON. Daily production uses ChatGPT Scheduled Work for the five scheduled super-jobs and connected GitHub UTF-8 text persistence. The repository contract itself does not create or enable schedules.

## Execution boundary

Production stays inside the user's existing ChatGPT Plus subscription. Forbidden: OpenAI API, `OPENAI_API_KEY`, pay-as-you-go OpenAI usage, GitHub Actions as external compute, paid external compute, self-hosted runners, and the user's PC as a production runtime dependency.

Tested Scheduled Work capabilities are recorded in `config/scheduled-workflow.yaml`. Connected GitHub text read/write/read-back PASS. Scheduled repository executable runtime is NOT AVAILABLE. GitHub image binary, PDF binary, and EPUB binary writes are UNSUPPORTED in the tested connector workflow.

Codex Cloud may be used manually later to render PDF/EPUB binaries from the persisted publication-source package. It is not part of the scheduled five-job execution and must not be scheduled unless a native supported mechanism exists in the future.

Final reader-facing publication semantics are authoritative in `config/final-publication.yaml`.

## Editorial topology

The 13 entries in `config/roles.yaml` remain authoritative editorial roles. They are coordinated through exactly five scheduled super-jobs:

- 07:45 — Current News Desk
- 08:00 — Deep Features Desk
- 08:50 — Chief Editor
- 09:25 — Publication Builder
- 09:55 — Cover Director

All use `Africa/Casablanca`. `config/schedule.yaml` remains disabled.

## Chief Editor hard gate

The final newspaper is Moroccan Darija written in Latin characters. Before Task 3 may be `COMPLETE`, scan the entire edition deterministically for Arabic-script characters in:

- U+0600–U+06FF
- U+0750–U+077F
- U+08A0–U+08FF
- U+FB50–U+FDFF
- U+FE70–U+FEFF

Locate every occurrence, rewrite/transliterate the intended text naturally into Moroccan Darija Latin without changing facts, rescan, and repeat until `arabic_script_count == 0`. Safe deterministic repair happens inside the same scheduled execution; do not require a separate human repair run merely because an initial scan found characters.

## Publication Builder

Scheduled Task 4 is TEXT-ONLY. It creates and persists:

- `edition.html`
- `print.css`
- `epub-content.xhtml`
- `publishing-report.json`

`publishing=COMPLETE` means **PUBLICATION SOURCE PACKAGE COMPLETE**. It does not mean PDF/EPUB binaries exist. Record:

- `pdf_binary = NOT_GENERATED_NO_RUNTIME`
- `epub_binary = NOT_GENERATED_NO_RUNTIME`
- `binary_artifacts = PENDING_MANUAL_CODEX_RENDER`
- `ready_for_codex_rendering = true`

## Cover Director

Task 5 uses a compact brief-first workflow: one lead, one cover mode, one dominant concept, minimal typography, DRAGON masthead, date, main headline, at most two teasers, black/white/red hierarchy, 3:4 portrait. Generate one image, run visual QA, and retry at most once with an even simpler composition if generation fails.

The first large all-in-one prompt failed in testing; minimal image generation and compact brief rendering passed. Do not reintroduce over-complex multi-stage prompts.

`cover=COMPLETE` means an actual generated cover passed visual QA. `SVG_FALLBACK` never counts as successful image generation. If image generation fails after the permitted retry, set `cover=FAILED`, keep the fallback only as a clearly labelled emergency text asset, and set final publication BLOCKED.

GitHub binary archival is separate because the tested connector cannot archive the generated image binary directly. Record normal generated-cover archival state as:

- `github_image_archive = UNSUPPORTED_BY_CONNECTOR`
- `cover_binary_archive = PENDING_MANUAL_ARCHIVE`

## Status semantics

`daily-runs/YYYY-MM-DD/status.json` has five scheduled stage fields: `current_research`, `deep_research`, `editorial`, `publishing`, `cover`, each using `PENDING`, `RUNNING`, `COMPLETE`, `BLOCKED`, or `FAILED`.

Binary/render/archive state is separate and must remain visible. Add and preserve `final_publication_status` using `PENDING`, `BLOCKED`, or `COMPLETE` as defined by `config/final-publication.yaml`.

Do **not** mark `overall_status=COMPLETE` merely because the five scheduled stages are done. `overall_status` must remain `PENDING` or `BLOCKED` until the final publication gate passes. Final publication `COMPLETE` requires a real generated cover plus validated PDF and EPUB binaries at their canonical GitHub paths with persistence/read-back verified.

A run may therefore have all five scheduled stage fields individually `COMPLETE` while `overall_status=PENDING` and `final_publication_status=PENDING`. This is expected when manual binary rendering is still pending.

Do not mark a text persistence step PASS merely because a file exists in temporary runtime. Connected GitHub write plus exact canonical read-back is required. Do not mark a binary published merely because it exists in temporary runtime either.

## Editorial depth and evidence

Use `config/editorial-depth.yaml`, `config/sources.yaml`, `config/quality-gates.yaml`, and `config/final-publication.yaml`. Major claims require traceable evidence. History, Literature/Culture, Morocco, Palestine, Meknes, and Science keep their configured depth gates. Investigations may remain explicitly non-publication-ready.

Do not weaken validators to finish on time.
