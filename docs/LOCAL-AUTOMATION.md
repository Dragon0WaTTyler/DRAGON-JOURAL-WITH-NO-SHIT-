# DRAGON V5 local automation

## Operating model

DRAGON V5 runs on the local Windows machine through one scheduled invocation of
`python dragon_daily.py`. That process owns the complete daily stage graph,
state, locking, logging, recovery, final local publication, archive, and
delivery. No desk, watchdog, GitHub workflow, or provider may independently
advance the same run.

This document is authoritative for V5 operation. It describes the target while
V4 remains available as a temporary fallback during staged migration.

## Commands

```text
python dragon_daily.py
python dragon_daily.py --resume
python dragon_daily.py --retry <stage>
python dragon_daily.py --from <stage>
python dragon_daily.py --status
```

The CLI and durable orchestration foundation are implemented. Stages without a
configured implementation fail closed with `STAGE_NOT_IMPLEMENTED`; this is an
explicit incomplete capability, not permission to use a second scheduler or to
claim a successful run.

## Ownership and checkpoints

The orchestrator executes the stage order in `SPEC-v5.md`. It acquires the daily
lock, loads or initializes atomic state, validates prerequisites, runs one stage
at a time, validates its outputs, records hashes, and advances. A valid
`COMPLETE` stage is reused by resume. `--retry` invalidates the selected stage
and downstream dependents only; `--from` deliberately reruns from a selected
boundary. Neither command changes a completed historical edition without an
explicit correction mode.

## Directories

```text
daily-runs/YYYY-MM-DD/
  state.json
  logs/
  research/
  articles/
  editorial/
  factcheck/
  qa/
  recovery/

editions/YYYY/MM/YYYY-MM-DD/
  edition.md
  sources.json
  edition-plan.json
  cover asset
  edition.html
  print.css
  dragon-YYYY-MM-DD.pdf
  dragon-YYYY-MM-DD.epub
  manifest.json
  publication report and receipts
```

Transient logs never belong in the edition directory. Historical V4 layouts
remain unchanged.

## Configuration and secrets

`config/local-automation.yaml` contains non-secret runtime policy. Provider
credentials come from environment variables or ignored local configuration.
Committed examples name variables but contain no credential values. Missing AI
or delivery configuration must be reported accurately during preflight.

## Preflight

Blocking checks cover repository identity, writable paths, configuration,
Python dependencies, network required by enabled stages, Git, storage, lock
state, Arabic fonts, PDF runtime, EPUB runtime, date/timezone, and required AI
provider capability. Optional archive or WhatsApp configuration is non-blocking
for local publication and may leave those stages `BLOCKED`, `FAILED`, or
`DEGRADED` according to policy.

## Completion semantics

Local publication completes only after the strict final gate. GitHub archive
and WhatsApp delivery remain independent. A report may truthfully state:

```text
publication = COMPLETE
github_archive = FAILED
whatsapp_delivery = FAILED
```

Recovery retries those external stages without rebuilding the newspaper.

## Migration safety

The V4 system remains enabled until `docs/LOCAL-CUTOVER.md` records the required
trials and authorizes retirement. During build-behind, V5 code must use explicit
V5 state and cannot treat legacy `status.json` as writable V5 state. GitHub
Actions remains a V4 fallback and CI service, not a V5 orchestrator.
