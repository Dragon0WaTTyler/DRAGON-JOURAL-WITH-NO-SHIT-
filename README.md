# DRAGON Daily Newspaper

Cloud-first newspaper workflow. GitHub is the permanent source of truth for
code, editorial memory, investigations, and archived editions. Production
must run in hosted Codex Cloud and must not depend on the user's PC.

The stage contract is in [config/pipeline.yaml](config/pipeline.yaml), and
Cloud credential rotation is documented in [SECURITY.md](SECURITY.md).
The subscription and execution boundary is enforced by
[config/execution-constraints.yaml](config/execution-constraints.yaml).

## Subscription boundary

Production is limited to the existing ChatGPT Plus subscription and hosted
Codex Cloud. The OpenAI API, `OPENAI_API_KEY`, pay-as-you-go OpenAI usage,
GitHub Actions calling the OpenAI API, external paid compute, self-hosted
runners, and a continuously online PC are forbidden. GitHub is only the
source-control, persistent-memory, archive, and artifact store.

Until native recurring Codex Cloud scheduling is available in this account,
production remains **manual hosted Cloud runs only**. The target remains
10:00 Africa/Casablanca using the existing pipeline unchanged.

## Current state

The repository has passed the infrastructure smoke test. The archived fixture
is **not journalism**. The recurring production schedule remains disabled.

Five real `PRE-PRODUCTION — NOT YET DAILY PRODUCTION` editions are archived
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

An edition must pass two kinds of gates: technical validity (artifacts,
manifest, citations, and persistence) and editorial depth. The depth policy is
centralized in [config/editorial-depth.yaml](config/editorial-depth.yaml),
and every real-edition validation writes
`research/YYYY-MM-DD/editorial-quality-report.json`. Source lists, metadata,
QA notes, and citation IDs do not count as article depth. Weak historical pilot
editions are intentionally rejected by the stronger validator and are not
rewritten to manufacture a pass.

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

The pre-production validator enforces the configured 4,000-word edition
minimum plus section minimums, the explicit Meknes thin-news exception, and
the investigations non-publication status rule. It also reports repeated-topic
matches and Chief Editor regeneration requests.

The archive gate is not complete until validation, commit, push, and remote
SHA verification all pass. An unpushed cloud commit is `NOT COMPLETE`.

## Pipeline runner

After Cloud editorial roles have written the nine packets, fact-check report,
and Darija gate report, run the deterministic pipeline wrapper:

```bash
python scripts/run_pipeline.py --date YYYY-MM-DD --dry-run
python scripts/run_pipeline.py --date YYYY-MM-DD
```

The dry run performs all configuration, packet, sequential-gate, and edition
checks. The normal run renders the six artifacts, stages only the dated
research/archive outputs plus `README.md`, commits, pushes `HEAD` to
`origin/main` without force, and requires an exact `git ls-remote` SHA match.
It refuses a dirty worktree, a non-cloud schedule, failed gates, or a missing
research packet. Use `--stage-path memory/...` or
`--stage-path investigations/...` when the Chief Editor changed persistent
editorial state during the same run.

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


Previous real pre-production editions: [2026-09-06](editions/2026/09/2026-09-06/edition.md), [2026-09-05](editions/2026/09/2026-09-05/edition.md), [2026-09-04](editions/2026/09/2026-09-04/edition.md), and [2026-09-03](editions/2026/09/2026-09-03/edition.md).

The [2026-09-02 edition](editions/2026/09/2026-09-02/edition.md) is the V1-candidate pre-production test; it is not daily production.
