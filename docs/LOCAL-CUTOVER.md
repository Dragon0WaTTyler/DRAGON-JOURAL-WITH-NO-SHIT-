# DRAGON V5 local cutover checklist

Cutover is an evidence decision, not a code-complete flag. Run
`python dragon_acceptance.py`; it exits nonzero until every required item below
is backed by hash-valid local artifacts and reviewed evidence.

## Required evidence

1. One explicit synthetic run completes local publication and visual Arabic PDF
   review confirms joined glyphs, RTL reading order, a canonical first-page
   cover, populated pages, and no catastrophic clipping.
2. One manually started **production** edition completes using a provider whose
   integration check is recorded as `PASS`. An editor reviews facts, Arabic,
   sources, PDF, EPUB, and the archive receipt.
3. At least three consecutive dated production editions start through the
   watchdog, complete without manual intervention, and retain hash-valid
   checkpoints and reports.
4. At least one real edition has a verified Git remote read-back receipt.
   WhatsApp is required only if `require_whatsapp_delivery` is enabled in
   `config/cutover-acceptance.yaml`.
5. `acceptance/evidence/failure-injection.json` records the stage-failure,
   resume, dependency, lock, corrupt-state, Git, and delivery scenarios that
   were exercised, with `status: PASS` and a human `reviewed_by` value.
6. `acceptance/evidence/artifact-comparison.json` records human comparison of
   the V5 real edition with the V4 product: depth, section decisions, source
   traceability, Arabic quality, cover, typography, PDF, and EPUB.
7. `acceptance/evidence/scheduler-trial.json` records the Windows task name,
   exactly one matching enabled task, start/deadline behavior, watchdog recovery
   observation, `status: PASS`, and `reviewed_by`.

Evidence files must contain genuine observations. Do not create placeholder
`PASS` files to satisfy the audit.

Run `python dragon_chaos_check.py` to create the machine side of item 5. It
executes the explicit process-interruption, network-timeout, EPUB-corruption,
PDF, Git, WhatsApp, stale-lock, and invalid-article scenarios and writes a
runtime-bound receipt plus hashed JUnit XML under
`acceptance/machine/failure-injection/`. The command deliberately records
`human_review_status: NOT_REVIEWED`; a human must inspect it and cite its exact
receipt/JUnit hashes from `failure-injection.json`.

Each review file uses schema version 5 and must contain a timezone-aware
`reviewed_at`, a real `reviewed_by`, the current `runtime_fingerprint`, every
check named for that file in `config/cutover-acceptance.yaml` with value
`PASS`, and a nonempty `evidence` mapping from repository-relative artifact
paths to their SHA-256 hashes. The audit recomputes those hashes and rejects
paths outside the repository or a review file that cites itself. The scheduler
review additionally requires the configured `task_name` and
`matching_enabled_tasks: 1`. A representative shape is:

```json
{
  "schema_version": 5,
  "status": "PASS",
  "reviewed_by": "<human operator>",
  "reviewed_at": "2026-09-08T12:00:00+01:00",
  "runtime_fingerprint": "<current fingerprint>",
  "checks": {"<configured check>": "PASS"},
  "evidence": {"<relative evidence path>": "<sha256>"}
}
```

The audit also rejects a run whose declared `run-report.json` does not match its
date, run ID, and completed publication state. GitHub and WhatsApp evidence is
accepted only when the receipt bytes still match a `COMPLETE` stage checkpoint;
an edited or loose receipt cannot satisfy cutover.

## Activation sequence

Only after the audit returns `READY_FOR_CUTOVER`:

1. Disable the five saved ChatGPT Scheduled Work production jobs and record the
   external task inventory in the scheduler evidence.
2. Remove autonomous production triggers from GitHub while retaining CI and
   archive verification.
3. Set the V5 cutover flags truthfully: legacy fallback disabled, local
   scheduler enabled, and competing GitHub production disabled.
4. Install/test the one Windows task without `-AllowBeforeCutover` and rerun the
   audit. It must return `CUTOVER_COMPLETE`.

If any activation check fails, disable the local task and restore the documented
V4 fallback. Historical editions and states are never rewritten during rollback.
