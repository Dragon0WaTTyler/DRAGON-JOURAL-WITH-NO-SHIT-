# DRAGON V5 local migration audit

Audit date: 2026-09-07

Repository: `Dragon0WaTTyler/DRAGON-JOURAL-WITH-NO-SHIT-`

Audited baseline: `3f75f4bd1005a5932c603a8a786027bcf94b1f01` on `main`

Baseline verification: `python scripts/validate_configuration.py` passed; 88 unit tests passed and 2 native WeasyPrint smoke tests were skipped on Windows as designed.

This is the Milestone 0 audit for the V5 migration. It records the current system before production behavior changes. Historical editions and daily status files are migration inputs and must remain immutable.

## 1. Current architecture summary

V4 is a cloud-first, repository-mediated pipeline. Five independent ChatGPT Scheduled Work jobs perform current-news research, deep-feature research, chief editing, cover direction, and publication-source assembly. They communicate by conditionally merging `daily-runs/YYYY-MM-DD/status.json` and committing text artifacts to GitHub. The jobs are separated by clock time, but they still verify prerequisite artifacts and Git blob identities rather than treating elapsed time as a dependency guarantee.

GitHub Actions then supplies the executable runtime that Scheduled Work lacks. `.github/workflows/publish.yml` polls today/yesterday and reacts to source-package pushes, runs deterministic validation, renders PDF and EPUB, commits the binaries, fetches them back, verifies SHA-256 identities, and makes a second finality commit. Separate workflows validate the current-news handoff, reject Arabic script, run the test suite, and monitor daily completion.

The design already has strong deterministic components: exact input lineage, source-package validation, semantic article-to-plan mapping, safe canonical-cover resolution, restricted renderer resource loading, EPUB structure checks, two-phase GitHub binary archival, and finality guards. What it does not have is a single local owner, a general stage interface, durable per-stage attempts and failure history, atomic local state writes, a recovery engine, an incident format, a watchdog, provider interfaces, or one Windows scheduler entry.

## 2. Current production entry points

| Entry point | Current purpose | V5 relevance |
| --- | --- | --- |
| Five external tasks described by `prompts/scheduled/01-current-news.md` through `05-publication.md` | Primary editorial production engine | Replace as scheduler/orchestration entry points; reuse editorial content rules in stage prompts/providers |
| `.github/workflows/publish.yml` | Automatic validation, binary rendering, Git commits, remote read-back | Refactor into optional CI/archive verification; remove autonomous production polling only after cutover acceptance |
| `scripts/auto_publish.py` | Idempotent binary-only GitHub publisher | Refactor into local archive stage plus reusable rendering/finality helpers |
| `scripts/render_production_binaries.py` | Compatibility CLI for local structural rendering | Keep as a compatibility wrapper around the renderer |
| `scripts/run_pipeline.py` | Legacy pre-production validator/renderer/pusher | Retire from production; retain temporarily for historical regression coverage |
| `scripts/publish_preproduction_edition.py` and `scripts/publish_smoke_edition.py` | Legacy fixture/pre-production publication | Retain as non-production fixtures until equivalent tests exist, then retire or isolate |

The preferred V5 entry point should be a repository-root `dragon_daily.py` thin CLI backed by a `dragon/` package. It will own `run`, `--resume`, `--retry STAGE`, `--from STAGE`, and `--status`.

## 3. Scheduled-work and GitHub assumptions

Current contracts in `AGENTS.md`, `README.md`, `SPEC-v1.md`, `prompts/production-master.md`, `config/schedule.yaml`, `config/scheduled-workflow.yaml`, and `config/execution-constraints.yaml` explicitly require:

- five active ChatGPT Scheduled Work jobs in `Africa/Casablanca`;
- ChatGPT Plus as the judgment-heavy runtime, with no OpenAI API billing;
- GitHub as the handoff and source of truth between independently scheduled jobs;
- conditional GitHub writes and exact remote text read-back;
- no local-PC dependency and no self-hosted runner;
- GitHub-hosted Ubuntu as the binary renderer and archive writer;
- Scheduled Work to create text publication sources but not PDF/EPUB bytes.

These assumptions directly conflict with V5. They must remain documented as V4 history while active authority moves to one local orchestrator. Editing repository prompts does not alter the user's five externally saved ChatGPT schedules, so retirement requires an explicit cutover checklist outside code.

## 4. Current handoffs and state model

The current high-level handoff is:

`current-news.json + deep-features.json -> edition-plan.json + edition.md + sources.json + editorial-report.json -> cover-brief.json + canonical cover -> edition.html + print.css + epub-content.xhtml + manifest.json -> PDF + EPUB -> GitHub binary read-back`

`scripts/workflow_state.py` creates and validates a flat `status.json`. Stage values support `PENDING`, `RUNNING`, `COMPLETE`, `BLOCKED`, and `FAILED`; final publication is intentionally restricted to `PENDING`, `BLOCKED`, or `COMPLETE`. Status includes many stage-specific fields, but it has no uniform stage record containing prerequisites, attempts, timestamps, errors, output hashes, and history. V5 must migrate rather than overwrite this schema: load legacy status read-only, map recognized fields into the new state model, preserve unknown fields under migration metadata, and never rewrite historical runs merely to normalize them.

Current retry behavior is fragmented:

- conditional GitHub status writes retry SHA conflicts up to three times in the scheduled-job contract;
- blocked scheduled stages wait for a later external invocation;
- `publish.yml` polls every 30 minutes and `auto_publish.py` retries today/yesterday candidates;
- `auto_publish.py` stops after the first failed edition and leaves truthful partial state;
- cover generation permits one simpler retry;
- there is no common classification, bounded backoff policy, targeted repair framework, incident packet, or process-resume watchdog.

## 5. Current publication paths

### Cover

`daily-runs/YYYY-MM-DD/cover-brief.json` is authoritative. It declares an exact asset beneath the dated edition directory. `scripts/publication_inputs.safe_asset` prevents traversal and prevents choosing a convenient alternate image. V4 accepts `AI_GENERATED` bytes or a self-contained `SVG_FALLBACK`; the latter is valid but must not be reported as successful image generation. `design/DRAGON-COVER-STYLE.md` and `templates/cover-v4.svg` define the visual system.

### Publication source

`scripts/build_publication_source.py` converts canonical Markdown and the edition plan to semantic HTML/XHTML. It preserves story/section/format mappings and exact source links. It currently hard-codes `lang="ary-Latn"`, `dir="ltr"`, `Tahrir: DRAGON`, and an Arabic-script count of zero.

### PDF

`scripts/publication_renderer.py` uses WeasyPrint for the interior, creates a 3:4 PDF cover page from the exact canonical cover, and combines them with `pypdf`. Its fetcher blocks network resources and path escape. `scripts/publication_inputs.py` validates freshness and lineage before rendering. PDF validation exists both in the production input/renderer path and the older `scripts/validate_edition.py` path.

### EPUB

`scripts/publication_renderer.py` creates a real ZIP/EPUB with stored `mimetype`, `META-INF/container.xml`, OPF, navigation, cover page/image, CSS, and reflowable article XHTML. It checks XML, manifest/spine references, resources, IDs, links, fragments, and `dcterms:modified`. It currently declares `ary-Latn` and left-to-right progression. The older pre-production renderer also builds EPUB but is not the current production path.

### Finality and archive

`scripts/auto_publish.py` performs a sound two-phase archive: render and commit binaries with final state still pending, fetch/read back hashes, then commit verified final state and update `memory/publication-ledger.json`. A finality guard prevents implicit regeneration of an already verified edition. This logic should be decomposed and reused; V5 must not require GitHub success for local publication completeness, but archive status must remain independently truthful.

## 6. Current validators and tests

Validators cover configuration contracts, research packet shape and exact URLs, current-news handoff completeness, editorial depth, fixed section inventory, article shape, semantic HTML mapping, source-package freshness and lineage, canonical cover safety, restricted resources, PDF/EPUB structure, reader-facing leakage, workflow state, daily completion, and Git archive read-back.

The untouched suite contains 88 passing tests. Two real WeasyPrint render tests are skipped on this Windows machine because the required native libraries are unavailable; CI explicitly enables them on Linux. This is a preflight finding, not a test failure. V5 Windows preflight must prove a working Arabic-capable PDF runtime before claiming local PDF support.

## 7. Source policy and continuity

`config/sources.yaml`, `config/output-schema.json`, `scripts/validate_story_packet.py`, and the role prompts already distinguish discovery from proof, require exact claim-level URLs, reject homepages as evidence, prefer primary and independent sources, preserve uncertainty labels, and warn that repeated syndication is not independent corroboration. Source pages are treated as untrusted data. This policy should be retained and made a provider-independent research-stage contract.

Continuity currently lives in `memory/covered-stories.json`, `history-used.json`, `literature-used.json`, `psychology-used.json`, `watchlist.json`, `publication-ledger.json`, and persistent dossiers under `investigations/`. The chief editor is instructed to read prior editions and memory. There is no transactional update protocol across this continuity data, so V5 should update it only after final publication QA and use atomic writes.

## 8. Arabic/LTR coupling and conflicting contracts

The following active areas are coupled to Darija Latin or LTR and must migrate as one compatibility boundary:

- authority: `AGENTS.md`, `README.md`, `SPEC-v1.md`, `PREPRODUCTION.md`, `prompts/production-master.md`;
- scheduled prompts: all five files under `prompts/scheduled/`, especially chief editor, cover, and publisher;
- roles: `agents/darija-editor.md` plus byline/language wording in editor and publishing roles;
- configuration: `editorial.yaml`, `editorial-depth.yaml`, `edition-architecture.yaml`, `pipeline.yaml`, `quality-gates.yaml`, `scheduled-workflow.yaml`, `roles.yaml`, `output-schema.json`, and manifest metadata;
- code: `editorial_depth.py`, `publication_inputs.py`, `build_publication_source.py`, `publication_renderer.py`, `validate_edition.py`, `validate_configuration.py`, and legacy publishers;
- templates/styles: `publication-v4.html`, `print-v4.css`, `edition-architecture.md`, `cover-v4.svg`, and story/cover examples;
- CI/tests: `reader-language.yml`, Arabic-script tests, reader-facing/EPUB tests, workflow-state tests, automatic-publication fixtures, editorial-depth fixtures, and scheduled-contract tests.

The most dangerous contradiction is executable: the current code rejects any Arabic script, emits `ary-Latn`/LTR HTML, and treats RTL EPUB metadata as an error. V5 requires the inverse. A prompt-only language change would therefore fail publication deterministically.

Other contract conflicts to reconcile:

- `config/pipeline.yaml` describes an older nine-packet hosted-cloud pipeline while active V4 uses two aggregate research handoffs and five scheduled jobs;
- `scripts/run_pipeline.py` requires `config/schedule.yaml.enabled == false`, while active V4 requires it to be true; README correctly labels the runner legacy;
- old pre-production code uses fixed filenames and manifest semantics different from current `dragon-YYYY-MM-DD.*` production artifacts;
- current finality makes GitHub read-back part of publication completion, while V5 needs local publication completion and archive/delivery as separate states;
- V4 combines fact check and Darija QA inside the chief-editor scheduled job even though artifacts exist for sequential gates; V5 requires distinct orchestrated stages.

## 9. KEEP / REFACTOR / REPLACE / RETIRE

| Decision | Components | Reason |
| --- | --- | --- |
| KEEP | source priority and verification policy; exact URL/story packet validation; edition plan and active-or-skipped section inventory; article-format/depth gates; canonical edition/source concepts; semantic story mapping; canonical-cover path safety; restricted renderer fetcher; EPUB structural checks; hash utilities; immutable finality guard principles; continuity dossiers and publication ledger; existing historical editions | These are proven deterministic/editorial safeguards and do not depend on the cloud scheduler model |
| REFACTOR | `workflow_state.py`; `publication_inputs.py`; `build_publication_source.py`; `publication_renderer.py`; `auto_publish.py`; `audit_daily_run.py`; configs, prompts, roles, templates, CSS, and current tests; GitHub workflows | Generalize into V5 stages, atomic local state, Arabic/RTL output, local completion semantics, separate archive receipt, and reusable stage-level validation |
| REPLACE | five-job orchestration; flat same-day status as the only state; Arabic-zero/Darija-Latin language gate; GitHub as the primary handoff bus; GitHub polling as production trigger; hard-coded byline; implicit retry-by-next-schedule | These directly contradict one local orchestrator, resumability, Arabic-first publishing, provider abstraction, and truthful recovery |
| RETIRE AFTER CUTOVER | external five ChatGPT schedules as production; autonomous `publish.yml` schedule; `reader-language.yml` Arabic rejection; legacy `run_pipeline.py`, smoke/pre-production publishers, and obsolete V3 contracts as production paths | They would compete with or misvalidate V5. Keep them available during trials and remove/disable only after acceptance |

No file should be removed during the build-behind phase unless it is proven unused and covered by replacement tests. Historical run and edition files are never migration cleanup targets.

## 10. Proposed V5 component graph

```text
Windows Task Scheduler (one entry)
        |
        v
dragon_daily.py ---- status/report CLI
        |
        +---- process lock / run identity ---- watchdog
        |
        v
LocalOrchestrator
        |
        +---- StateStore (atomic state.json + backup + legacy importer)
        +---- StageRegistry / StageContext / artifact hashing / stage logs
        +---- ErrorClassifier + RecoveryEngine + recovery-policy.yaml
        +---- IncidentWriter ---- RepairAgent interface ---- optional tested local backend
        |
        v
preflight -> research -> article_generation -> chief_editor -> factcheck
          -> arabic_language_qa -> cover -> publication_source -> pdf -> epub
          -> final_qa
                    |
                    +-> github_archive (independent receipt/status)
                    +-> whatsapp_delivery (provider interface; independent receipt/status)

Canonical work: daily-runs/YYYY-MM-DD/{state.json,logs,research,articles,editorial,factcheck,qa,recovery}
Canonical output: editions/YYYY/MM/YYYY-MM-DD/{edition.md,sources.json,edition-plan.json,cover,html,pdf,epub,manifest,receipts}
```

Each stage record must contain its name, prerequisites, declared inputs/outputs, status, start/end times, attempt count, stable error code/detail, artifact hashes, and recovery history. Completion is granted only by that stage's validator. A downstream retry consumes the last valid upstream checkpoint without regenerating it.

AI-dependent stages must call explicit provider interfaces. The repository currently proves no supported unattended local AI backend and no WhatsApp provider. V5 may ship mock/manual adapters and clean interfaces, but must report those capabilities as unavailable until an actual configured integration passes an integration test. No paid API or credential may be introduced silently.

## 11. Migration risks

| Risk | Consequence | Mitigation / acceptance evidence |
| --- | --- | --- |
| Arabic shaping/runtime unavailable on Windows | PDF exists but glyphs are broken or blank | Blocking preflight for configured Arabic font and real renderer; render/extract test with representative mixed-direction fixture |
| Partial language migration | Arabic edition blocked by surviving V4 zero-Arabic/LTR gate | Central Arabic QA module plus repository-wide regression scan and RTL HTML/EPUB tests |
| False checkpoint completion | Resume skips invalid output | Stage-specific acceptance validators and hashes, never existence-only checks |
| State corruption on crash | Only resume record is lost | temp-file write, flush/fsync where supported, atomic replace, previous-good backup, corruption recovery test |
| Duplicate scheduler/watchdog process | Concurrent editions or conflicting writes | OS/process lock with run ID, PID/start-time validation, stale-lock policy, duplicate-start test |
| AI backend absent or interactive | Unattended editorial run stalls | Preflight capability detection; explicit provider state; incident packet/manual intervention rather than fake completion |
| Automated repair damages code or artifacts | Larger outage or corrupted edition | isolated branch/worktree, minimal diff, targeted and regression tests, protected artifacts, automatic rollback |
| GitHub history divergence or rejected push | Archive fails after valid local publication | Archive-only retry, normal push, fetch/read-back hashes, publication remains COMPLETE while archive is FAILED |
| WhatsApp provider limitations/cost/credentials | Delivery fails or creates surprise billing | provider abstraction, opt-in config and environment secrets, mock tests, delivery status isolated from publication |
| Old schedulers still active | Competing V4 and V5 editions | staged cutover, inventory of external schedules/workflows, explicit disable verification only after trials |
| Migration mutates historical data | Loss of trustworthy evidence | legacy importer, date-scoped new state, immutable-history tests, no bulk rewrites |
| Large all-at-once refactor | Hard rollback and unclear regressions | small milestone commits built behind V4, with baseline and targeted tests at each boundary |

## 12. Ordered implementation milestones

The 29 requested milestones are grouped into rollback-safe delivery increments while preserving their acceptance order:

1. **Audit and baseline (M0):** this document, clean revision, baseline tests, architecture decisions.
2. **V5 authority (M1):** reconcile `AGENTS.md`, README, specification, and local automation contract; mark V4 as migration history without disabling it.
3. **Arabic-first core (M2, M3, M13-M16):** Arabic headings/byline configuration, research/article/editor/fact-check/language-QA contracts, deterministic UTF-8/RTL/mojibake/leakage validators, migrated templates and fixtures.
4. **Orchestrator foundation (M4, M5, M7):** package, CLI, stage interface, atomic state store, legacy-state importer, run directories, structured stage logs.
5. **Preflight and recovery (M6, M8-M11):** machine checks, classifier, policies, targeted retries, incident packets, safe `RepairAgent` interface with truthful capability detection.
6. **Watchdog and scheduler (M12, M23):** lock semantics, stale-run recovery, one Windows scheduled entry, install/remove/test/run-now scripts.
7. **Publication stages (M17-M20):** final-edition cover, Arabic PDF, real RTL EPUB, strict final gate, flexible pages, isolated validators.
8. **Archive and delivery (M21-M22):** GitHub archive/read-back stage and opt-in WhatsApp provider interface; neither invalidates local publication.
9. **Verification and reporting (M24-M26):** unit/integration/regression/chaos tests and concise machine/human run reports.
10. **Cutover and acceptance (M27-M28):** synthetic, manual-real, consecutive unattended trials, failure injection, provider-dependent checks, and only then retirement of competing production schedules.

## 13. Expected files

Likely additions (exact package boundaries may be refined without changing the architecture):

- `dragon_daily.py`
- `dragon/` modules for orchestrator, stages, state, locking, logging, preflight, recovery, incidents, watchdog, reports, providers, and publication adapters
- `config/local-automation.yaml`, `config/recovery-policy.yaml`, `.env.example`
- `docs/LOCAL-AUTOMATION.md`, `docs/RECOVERY-RUNBOOK.md`, `docs/FAILURE-CATALOG.md`, `docs/LOCAL-CUTOVER.md`
- Windows scheduler/watchdog install, remove, test, and run-now scripts under `scripts/windows/`
- V5 unit, integration, renderer, provider-mock, resume, watchdog, and chaos tests under `tests/`

Expected modifications:

- `AGENTS.md`, `README.md`, `SPEC-v1.md` or a V5 successor, `PREPRODUCTION.md`, `requirements.txt`
- active configs under `config/`, especially schedule, roles, pipeline, quality, architecture, language, execution, and publication semantics
- editorial and scheduled prompts under `prompts/` and role contracts under `agents/`
- publication templates/CSS and cover contract under `templates/` and `design/`
- deterministic publication/validation helpers under `scripts/`
- CI workflows, preserving test verification while removing production competition only at cutover

Expected removal at final cutover: none is assumed. Obsolete production entry points can first be moved to an explicitly documented legacy status; physical deletion requires a later usage audit and replacement coverage.

## 14. Tests protecting the migration

Before each increment, preserve the current 88-test suite and document expected contract changes rather than weakening assertions. Add:

- state transition, prerequisite, attempt, checkpoint, and finality tests;
- atomic-write interruption/corruption/backup recovery tests;
- `--resume`, `--retry`, `--from`, and `--status` CLI tests;
- lock ownership, duplicate-run, stale-lock, dead-process, and watchdog-resume tests;
- error classification, bounded backoff, targeted recovery, max-attempt, and incident-redaction tests;
- Arabic UTF-8, script presence, `lang="ar"`, `dir="rtl"`, mixed-direction names, punctuation, mojibake, leakage, and font-preflight tests;
- real Arabic PDF render/open/extraction/cover/content/blank-page checks on the supported Windows runtime;
- EPUB ZIP, OPF, nav, manifest, spine, RTL progression, Arabic metadata, cover, resources, XML, UTF-8, and source-link tests;
- synthetic success and interruption at every expensive checkpoint;
- injected research, article, PDF, EPUB, Git, WhatsApp, invalid-output, and stale-lock failures;
- verification that GitHub/WhatsApp failures retry only their stages and do not invalidate a completed publication;
- provider contract tests proving unavailable integrations are reported honestly;
- immutable historical edition/status regression tests;
- cutover test proving only one enabled production scheduler remains.

## 15. Milestone 0 conclusion

The V5 migration is feasible without discarding V4. The lowest-risk path is to retain the editorial architecture and deterministic publication safeguards, introduce a new local orchestration/state/recovery layer beside V4, migrate Arabic and renderer semantics behind explicit V5 contracts, and retire cloud triggers only after real unattended acceptance runs. No current component provides a proven unattended local AI or WhatsApp implementation; those capabilities must remain provider-gated and truthfully unavailable until configured and tested.
