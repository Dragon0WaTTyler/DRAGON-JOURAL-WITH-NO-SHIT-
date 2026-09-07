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

For a deterministic local acceptance run only:

```text
python dragon_daily.py --synthetic --date 2099-01-02
```

Synthetic mode is visibly labelled in preflight, research, fact-check, cover,
final-QA, and manifest artifacts. It bypasses production network and AI checks
solely to verify orchestration and publication mechanics. It is not an
editorial substitute and cannot be selected implicitly. The production
provider remains fail-closed until it is configured and integration-tested.

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

## GitHub archive

The `github_archive` provider is disabled during build-behind. When explicitly
enabled with type `git-cli`, it stages only files beneath the dated edition
directory, creates a normal non-force commit when needed, pushes the configured
branch, fetches the remote ref, and compares the SHA-256 of every remote blob
with the exact local file. Its receipt records both commit identities and every
verified artifact. A rejected push or byte mismatch fails only the archive
outcome; an already completed local publication stays complete and archive-only
retry reuses its checkpoints.

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

## Windows scheduler and watchdog

The single Task Scheduler entry invokes `dragon_watchdog.py` at the configured
start time and repeats the same entry at the configured interval. The watchdog
starts `dragon_daily.py` when today's run is absent. It resumes only when state
contains a `RUNNING` stage and the lock owner is absent or provably dead. A live
process with a stale heartbeat produces diagnostics and is never duplicated.

```text
powershell -File scripts/windows/install-scheduler.ps1
powershell -File scripts/windows/test-scheduler.ps1
powershell -File scripts/windows/run-now.ps1
powershell -File scripts/windows/remove-scheduler.ps1
python dragon_watchdog.py --check-only
```

Installation refuses while `scheduler.enabled` is false unless the operator
explicitly uses `-AllowBeforeCutover` for a trial. `MultipleInstances=IgnoreNew`
and the repository run lock provide independent duplicate-run protection.
