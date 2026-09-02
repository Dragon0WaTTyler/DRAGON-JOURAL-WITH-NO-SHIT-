# DRAGON Daily Newspaper — Technical Specification v1

## Scope

One hosted Codex Cloud run produces one real or synthetic archived edition.
The system has 13 editorial roles, but does not require 13 persistent
processes. Research can be parallel; editorial gates are sequential.

The first archived run is a synthetic smoke test. The next required milestone
is a real pre-production edition. Recurring production is forbidden until the
pilot and PC-off acceptance test pass.

## Roles and topology

The authoritative role registry is `config/roles.yaml`. The roles are:

1. Chief Editor / Orchestrator
2. Morocco Desk
3. Meknes Intelligence Desk
4. Palestine & Middle East Desk
5. World Geopolitics Desk
6. AI & Technology Desk
7. Science Research Desk
8. Tarikh l-Mghreb Desk
9. Adab & Culture Desk
10. Investigations & Accountability Desk
11. Fact-check Desk
12. Darija Language Editor
13. Creative Director / Publishing Desk

Research roles return structured packets, not disconnected final articles.
Packets use `config/output-schema.json`. The Chief Editor owns selection,
ranking, synthesis, rejection, and the final voice.

## Research and continuity

Each run reads and updates durable repository state:

- `memory/` for covered stories, front pages, topics, studies, and watchlists;
- `investigations/` for multi-day dossiers;
- `research/YYYY-MM-DD/` for that run's packets;
- `editions/` for the canonical published record.

No container state or temporary attachment is authoritative. Investigations
must record supporting and contradictory evidence and may only move to
`READY` when the Chief Editor decides the evidence is sufficient.

## Sequential quality gates

1. research packets and source records exist;
2. major claims are verified and attributed;
3. unsupported accusations are held or removed;
4. History and Culture meet justified long-form depth;
5. Darija Latin language gate passes with zero Arabic-script characters;
6. citations support the relevant claims;
7. PDF, EPUB, cover, manifest, and Markdown validate;
8. commit, push, and exact remote SHA verification pass.

Each fact-check issue is `PASS`, `FIX`, or `REMOVE`. A required `FIX` or
`REMOVE` blocks publication until resolved.

## Artifact and manifest contract

The edition directory is:

```text
editions/YYYY/MM/YYYY-MM-DD/
```

It must contain `edition.md`, `edition.pdf`, `edition.epub`, `cover.webp`,
`sources.json`, and `manifest.json`. `edition.md` is the master text. The PDF
is fixed-layout and the EPUB is reflowable with a navigation document; the
EPUB must not be a fake copy of newspaper columns.

Smoke manifests have `smoke_test: true`. Real pre-production manifests have
`smoke_test: false`, `mode: preproduction`, `status: pre-production`, passed
fact-check and language states, and a nonzero source count. The validator
enforces the mode-specific contract.

## Cloud-only and persistence semantics

Production is hosted Codex Cloud only. Network access must be explicitly
enabled for research. GitHub credentials remain in the configured secure
Cloud setup and never enter the repository or logs.

The run is `NOT COMPLETE` if validation, commit, push, or remote SHA
verification fails, even when files exist inside the temporary Cloud
container.

## Schedule and acceptance

`config/schedule.yaml` stays disabled during smoke, pre-production, review,
second-run, and pilot stages. After the pilot, configure the recurring Cloud
run for 10:00 `Africa/Casablanca`, then perform a genuine PC-off test. Only
after the scheduled run creates and remotely verifies a complete edition may
the project be called `PRODUCTION CLOUD-ONLY CONFIRMED`.
