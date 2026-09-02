# DRAGON Daily Newspaper

Cloud-first newspaper workflow. GitHub is the permanent source of truth for
code, editorial memory, investigations, and archived editions. Production
must run in hosted Codex Cloud and must not depend on the user's PC.

## Current state

The repository has passed the infrastructure smoke test. The archived fixture
is **not journalism**. The recurring production schedule remains disabled.

Four real `PRE-PRODUCTION — NOT YET DAILY PRODUCTION` editions are archived
for quality review. Pilot editions remain non-recurring pre-production.

## Repository contract

```text
agents/                  role instructions
config/                  roles, models, sources, gates, permissions, schedule
research/YYYY-MM-DD/     structured research packets for a run
memory/                  durable editorial continuity
investigations/          persistent evidence-led dossiers
editions/YYYY/MM/DATE/   canonical text and published derivatives
scripts/                 generation and validation tools
templates/               human-readable packet templates
```

Each edition contains:

```text
edition.md       canonical Darija Latin master
edition.pdf      fixed-layout derivative
edition.epub     reflowable derivative
cover.webp       editorial cover asset
sources.json     traceable source records
manifest.json    machine-checkable publication state
```

## Validation

Smoke fixture:

```bash
python scripts/publish_smoke_edition.py --date YYYY-MM-DD
python scripts/validate_edition.py --date YYYY-MM-DD --mode smoke
```

Real pre-production edition (run from hosted Codex Cloud after editorial
work is complete):

```bash
python scripts/validate_edition.py --date YYYY-MM-DD --mode preproduction
```

The archive gate is not complete until validation, commit, push, and remote
SHA verification all pass. An unpushed cloud commit is `NOT COMPLETE`.

See [AGENTS.md](AGENTS.md), [SPEC-v1.md](SPEC-v1.md), and
[PREPRODUCTION.md](PREPRODUCTION.md) for the operating contract.

## Latest archived fixture
2026-09-02

- [Markdown](editions/2026/09/2026-09-02/edition.md)
- [PDF](editions/2026/09/2026-09-02/edition.pdf)
- [EPUB](editions/2026/09/2026-09-02/edition.epub)


## Latest pre-production edition
2026-09-07 — **PRE-PRODUCTION — NOT YET DAILY PRODUCTION**

- [Markdown](editions/2026/09/2026-09-07/edition.md)
- [PDF](editions/2026/09/2026-09-07/edition.pdf)
- [EPUB](editions/2026/09/2026-09-07/edition.epub)
- [Sources](editions/2026/09/2026-09-07/sources.json)
- [Manifest](editions/2026/09/2026-09-07/manifest.json)


Previous real pre-production editions: [2026-09-05](editions/2026/09/2026-09-05/edition.md), [2026-09-04](editions/2026/09/2026-09-04/edition.md), and [2026-09-03](editions/2026/09/2026-09-03/edition.md).

The [2026-09-02 smoke fixture](editions/2026/09/2026-09-02/edition.md) remains archived separately and is not journalism.
