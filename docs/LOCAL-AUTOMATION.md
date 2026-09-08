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

For a durable machine record of the required failure-injection scenarios:

```text
python dragon_chaos_check.py
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

Every run records a content-derived `runtime_fingerprint`. It covers the V5
Python package and entry points, editorial adapter, recovery policy, declared
dependencies, and Windows scheduler scripts. The final run report repeats the
same identity, and cutover acceptance requires it to match the current runtime.
An ordinary resume against changed runtime is blocked with
`RUNTIME_FINGERPRINT_MISMATCH`; after reviewing the change, the operator must
restart explicitly with `--from preflight` so old and new stage checkpoints are
never mixed. Deployment-only cutover switches and `scheduler.enabled` are
excluded from the fingerprint to avoid invalidating proven trials when the
accepted scheduler is activated.

Clean-worktree preflight enumerates individual untracked files. State-backed
V5 run/edition outputs and files beneath `acceptance/machine/`,
`acceptance/provider-trials/`, and `acceptance/evidence/` are allowed only while
untracked, so genuine local evidence does not block the first production run.
Any tracked modification in those directories—or any source/config change—
remains a blocking dirty-worktree failure.

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
verified artifact, plus the edition date, producing runtime fingerprint,
completed-publication state, and final manifest hash. A rejected push or byte
mismatch fails only the archive
outcome; an already completed local publication stays complete and archive-only
retry reuses its checkpoints.

## WhatsApp delivery

The opt-in `meta-cloud-api` adapter uploads the canonical PDF to Meta's media
endpoint and sends that media identifier as a document to each configured
recipient. The Graph API version is configuration, not a silently changing
default. Tokens, the sender phone-number ID, and comma-separated recipients are
read only from the environment names in `.env.example`. Receipts store provider
message IDs and hashes of recipients, never tokens or raw recipient numbers.
The stage wrapper also binds the receipt to production mode, edition date,
runtime fingerprint, completed publication, and the exact PDF SHA-256. Cutover
revalidates every one of those fields and every recipient acceptance record.

The capability remains unavailable until `enabled` is true,
`integration_test_status` is `PASS`, the version is explicit, and all required
environment values exist. A successful synchronous response is recorded as
`ACCEPTED_BY_PROVIDER`; it is not misrepresented as device delivery, which
would require separately authenticated webhook evidence.

## Preflight

Blocking checks cover repository identity, writable paths, configuration,
Python dependencies, network required by enabled stages, Git, storage, lock
state, Arabic fonts, PDF runtime, EPUB runtime, date/timezone, and required AI
provider capability. Optional archive or WhatsApp configuration is non-blocking
for local publication and may leave those stages `BLOCKED`, `FAILED`, or
`DEGRADED` according to policy.

The PDF capability probe encodes and reopens a real in-memory Pillow PDF after
Arabic reshaping/bidi initialization. When Git archive is enabled, preflight
also checks the configured Git author identity and performs a read-only
`ls-remote` of the exact archive branch. That archive probe remains
non-blocking: failure becomes an explicit warning and cannot erase an otherwise
valid local newspaper.

After an editorial integration has been marked `PASS`, every production
preflight also executes its `healthcheck` operation and requires a live
`status: PASS` plus `unattended: true`. A stale executable, expired login, or
interactive prompt therefore blocks before research rather than failing deep
inside the edition. Preflight also reruns the provider-trial evidence audit: a
manually edited configuration `PASS` cannot start research unless the current
runtime has a technically validated trial and its exact receipt has a later,
hash-bound human review.

## Completion semantics

Local publication completes only after the strict final gate. The final-QA
checkpoint directly consumes the hash-bound chief-editor,
fact-check, Arabic, PDF, EPUB, and cover reports and requires every mandatory
status to pass. Stage order alone is not accepted as proof of readiness.
GitHub archive and WhatsApp delivery remain independent. A report may
truthfully state:

```text
publication = COMPLETE
github_archive = FAILED
whatsapp_delivery = FAILED
```

The built-in deterministic cover is recorded as `COVER_FALLBACK`, never as AI
generation. A future image provider may use `COVER_GENERATED` only when an
actual durable local asset passes the same cover and publication validators.

When the official WhatsApp provider is enabled, its PDF caption contains the
completed-publication status, edition date, up to three chief-editor lead
headlines, and `providers.whatsapp.archive_link_template` when configured. The
template may contain `{date}`. Retry identity covers both the PDF and caption,
so changed delivery content cannot silently reuse an earlier partial receipt.

Recovery retries those external stages without rebuilding the newspaper.

Every owned invocation writes `run-report.json` and `run-report.txt` beneath
the dated run directory. They summarize elapsed time, local publication, cover,
PDF, EPUB, archive, WhatsApp, recovery actions, and unresolved warnings. These
operator reports are not stage checkpoints and do not alter edition hashes.

The report resolves `scheduler.target_deadline` in the configured local
timezone and records separate `publication_deadline_status` and
`delivery_deadline_status` values. Disabled or failed optional delivery is
reported as `NOT_COMPLETED`; it does not rewrite a completed publication as
failed.

A normal rerun of a locally complete, hash-valid edition returns
`ALREADY_PUBLISHED`. If any completed local checkpoint no longer matches its
recorded hash, the rerun returns
`COMPLETED_EDITION_CHECKPOINT_INVALID` and does not regenerate bytes. Repairing
or correcting such an edition requires an explicit `--from` or `--retry`
boundary and therefore leaves an auditable recovery history.

The Windows PDF backend flows long Arabic bodies across as many populated pages
as required. It never enforces a fixed page count or clips verified prose to fit
an article-sized canvas. Continuation pages repeat a compact story identifier;
exact source URLs flow at the end of the story and are also embedded as PDF URI
annotations. PDF QA requires every canonical article source URL to have a
matching clickable annotation.

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

Unsafe states use the explicit watchdog action `ATTENTION` and a nonzero task
exit code: unreadable state without a valid backup, unreadable locks, multiple
RUNNING stages, stale live heartbeats, and failed/blocked stages already marked
`REQUIRES_INTERVENTION`. These conditions are never disguised as idle
`NO_ACTION` and never trigger a duplicate process.

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
The test script inventories every task whose action invokes this repository's
watchdog, requires exactly one enabled match, verifies its single action,
single trigger, configured start/repetition, `IgnoreNew`, and
`StartWhenAvailable`, then atomically records runtime-bound inventory evidence
at `acceptance/machine/scheduler/inventory.json`. It does not prove unattended
publication by itself; the dated watchdog runs and human scheduler review remain
required.
