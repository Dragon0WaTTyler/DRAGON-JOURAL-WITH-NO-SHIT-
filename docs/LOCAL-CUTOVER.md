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
