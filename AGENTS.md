# Daily Newspaper — Codex Cloud operating contract

This repository is the source of truth for the DRAGON Daily Newspaper. The
production and pre-production workflow must execute in hosted Codex Cloud.
The local PC, localhost, desktop files, and a local process are never runtime
dependencies.

## Operating modes

There are two explicit modes:

1. `smoke`: synthetic content used only to test artifact creation, validation,
   commit, push, and remote-SHA verification. It must remain labeled
   `SMOKE TEST — NOT FOR PUBLICATION`.
2. `preproduction`: one real, current, fully cited newspaper run. It must be
   labeled `PRE-PRODUCTION — NOT YET DAILY PRODUCTION` and must not enable the
   recurring schedule.

Never represent a smoke fixture as journalism. Never use fixture content in a
pre-production edition.

## Editorial topology

Treat the 13 entries in `config/roles.yaml` as editorial roles, not as a
requirement for 13 persistent processes. The Chief Editor coordinates the
work. Research desks should run in parallel when Codex Cloud supports it and
return structured packets under `research/YYYY-MM-DD/`. Synthesis,
fact-check, Darija QA, publishing, validation, commit, and push are
sequential quality gates.

The Chief Editor must:

- read the current memory and investigations before choosing stories;
- assign work to the relevant desks and avoid duplicated research;
- compare primary, independent, and contradictory evidence;
- reject unsupported claims and weak filler;
- request focused follow-up research when uncertainty is material;
- write one coherent edition rather than pasting independent essays;
- preserve facts and citations through the language and design stages.

Each research packet must conform to `config/output-schema.json`. Each
investigation must conform to `config/investigation-schema.json` and retain
contradictory evidence as well as supporting evidence.

## Real-edition requirements

For `preproduction`, use real current web research and save source records.
Apply the source policy in `config/sources.yaml`. Important claims need
traceable citations. Label disputed claims, estimates, company claims,
abstract-only studies, and unknowns explicitly.

The final newspaper must be Moroccan Darija written in Latin characters.
Arabic-script characters in `edition.md` are a hard failure. Ordinary prose
must not become full English or French paragraphs. The language editor may
change style only, never factual meaning.

History and Culture are substantial features when their topics justify it;
they must include context, analysis, evidence, disagreement, and present
relevance. Meknes must use local and institutional sources and may publish an
honest `Meknes Radar` item when conventional news is thin. Palestine must
separate fact, claim, disputed claim, estimate, and unknown.

## Required artifacts

Every real edition directory must contain:

```text
edition.md
edition.pdf
edition.epub
cover.webp
sources.json
manifest.json
```

`edition.md` is the canonical master. PDF and EPUB are derivatives. The
manifest records mode, validation states, source count, and artifact names.

Run the validator with the matching mode:

```bash
python scripts/validate_edition.py --date YYYY-MM-DD --mode smoke
python scripts/validate_edition.py --date YYYY-MM-DD --mode preproduction
```

Do not mark an edition complete because files merely exist. The appropriate
content, language, source, PDF, EPUB, and manifest gates must pass.

## GitHub persistence gate

The daily run is complete only after all of these succeed, in order:

1. artifacts are generated;
2. validation passes;
3. fact-check and language gates are recorded as passed;
4. a commit succeeds;
5. push to `origin/main` succeeds;
6. `git ls-remote origin refs/heads/main` returns the exact pushed SHA.

If push or remote verification fails, status is `NOT COMPLETE`. Retry the
push without regenerating already successful editorial work. Never commit
secrets or print `GITHUB_TOKEN`.

## Scheduling and cloud-only acceptance

`config/schedule.yaml` must remain disabled until the real pre-production run,
quality fixes, a fresh second run, and the three-day pilot all pass. Only then
may the daily Cloud schedule be configured for 10:00 Africa/Casablanca.

The final acceptance test must run with the local desktop and PC unavailable
and verify that the scheduled hosted run creates, validates, commits, pushes,
and remotely verifies a complete edition.
