# DRAGON Daily Newspaper — Technical Specification v1

## Subscription and execution constraints

The production boundary is the user's existing ChatGPT Plus subscription.
Execution must happen in hosted Codex Cloud. The project must not use the
OpenAI API, require `OPENAI_API_KEY`, create pay-as-you-go OpenAI usage, call
the OpenAI API from GitHub Actions, use external paid compute, require a
self-hosted runner, or require the user's PC to stay online. GitHub remains
source control, persistent memory, edition archive, and artifact storage
only. Until native recurring Codex Cloud scheduling is available in this
account/setup, production runs are manual hosted Cloud runs only.

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

The declarative execution order and failure isolation policy are in
`config/pipeline.yaml`; it is a role/stage contract, not a requirement for
thirteen permanently running processes.

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
4. editorial-depth gates pass using the thresholds in
   `config/editorial-depth.yaml`;
5. Darija Latin language gate passes with zero Arabic-script characters;
6. citations support the relevant claims;
7. PDF, EPUB, cover, manifest, and Markdown validate;
8. the quality report is saved at
   `research/YYYY-MM-DD/editorial-quality-report.json`;
9. commit, push, and exact remote SHA verification pass.

Each fact-check issue is `PASS`, `FIX`, or `REMOVE`. A required `FIX` or
`REMOVE` blocks publication until resolved.

### Editorial depth policy

The validator parses Markdown H2 sections and counts narrative words only;
source lists, QA notes, metadata, preproduction labels, and citation IDs do
not satisfy depth. The edition hard minimum is 4,000 words. Hard section
minimums are History 800, Literature/Culture 800, Morocco 700, Palestine 500,
and Science 500. Meknes has a 300-word minimum with a narrowly-scoped,
explicit `THIN-NEWS EXCEPTION`; Investigations have a 600-word publication
minimum but may record a marked non-publication dossier update. World and AI
have configured target ranges. The report records counts, thresholds,
exceptions, repeated-topic review, and Chief Editor regeneration requests.

Technical validity alone cannot publish an edition. Existing pilot editions
are historical evidence and may fail this stronger policy; they must not be
edited solely to make the validator pass.

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

Credential rotation and the 2026-10-02 expiry checklist are documented in
`SECURITY.md`.

The run is `NOT COMPLETE` if validation, commit, push, or remote SHA
verification fails, even when files exist inside the temporary Cloud
container.

## Schedule and acceptance

`config/schedule.yaml` stays disabled during smoke, pre-production, review,
second-run, and pilot stages. After the pilot, configure the recurring Cloud
run for 10:00 `Africa/Casablanca`, then perform a genuine PC-off test. Only
after the scheduled run creates and remotely verifies a complete edition may
the project be called `PRODUCTION CLOUD-ONLY CONFIRMED`.

## Future Scheduled Work contract

Future ChatGPT Scheduled Work orchestration is specified in
`config/scheduled-workflow.yaml`. It coordinates the existing 13 editorial
roles through five super-jobs and uses `Africa/Casablanca`; it does not replace
the role registry or enable `config/schedule.yaml`. Cover generation follows
`design/DRAGON-COVER-STYLE.md`. These are contracts only. Production
activation requires tested native Scheduled Work behavior and verified text and
binary persistence, including a successful PC-off acceptance test.
