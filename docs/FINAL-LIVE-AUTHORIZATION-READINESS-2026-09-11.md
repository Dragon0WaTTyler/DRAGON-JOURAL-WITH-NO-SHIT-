# Final live authorization readiness audit — 2026-09-11

## Decision

`READY_FOR_FINAL_LIVE_AUTHORIZATION`

One newly authorized editorial-provider trial can now advance the V5 evidence
chain.  This is **not** `READY_FOR_CUTOVER`, `CUTOVER_COMPLETE`, or local
publication completion.  The trial remains subject to the existing provider,
provenance, fact-check, Arabic QA, publication-finality, archive read-back, and
human-review gates.

## Why the earlier report said `NOT_READY`

`docs/FINAL-CUTOVER-PREREQUISITES-2026-09-11.md` truthfully ran the existing
`dragon_acceptance.py` **cutover** audit.  Its `BLOCKED` result requires a
manual production edition, three watchdog production runs, a production Git
archive receipt, reviewed comparison/failure/scheduler evidence, and then
activation/retirement checks.  Those are necessarily later than an initial
successful provider trial.  Treating that post-trial cutover result as the
pre-trial authorization decision created a circular sequence:

```text
old interpretation: real edition -> provider trial -> live authorization -> real edition
correct sequence:   live authorization -> provider trial -> review/promotion
                    -> manual edition/archive/unattended trials -> cutover audit
```

The earlier report's deterministic findings remain valid: the scheduler is
paused, V4 fallback is preserved, and no fixture is claimed as a newspaper.
Only its final readiness label answered the wrong state-machine question.

## Implemented boundary

`dragon/live_readiness.py` and `dragon_live_readiness.py` add a fail-closed,
separate pre-live evaluator.  It requires all of the following before a new
trial may start:

- V5 is still in `build-behind`; the single V5 scheduler is disabled in
  repository configuration and all pre-cutover safety flags preserve V4.
- The editorial provider is a local command, has `NOT_RUN` integration state,
  and cannot auto-enable a paid service.
- The supplied local Codex automation record is the one expected DRAGON task,
  scoped to this saved project, uses the canonical watchdog command and daily
  schedule, and is `PAUSED`.
- No current-runtime technically valid receipt is waiting for human review and
  no current-runtime reviewed receipt already needs a human configuration
  promotion instead of another provider call.

It intentionally does **not** require manual production publication, archive
read-back, unattended production runs, human cutover evidence, scheduler
activation, disabling V4, or disabling the legacy GitHub production fallback.
Those remain in `dragon_acceptance.py` and `docs/LOCAL-CUTOVER.md`.

## Observed local state

The local Codex automation record at
`C:\Users\walid\.codex\automations\dragon-v5-daily-newspaper\automation.toml`
was inspected without modifying it.  It identifies `DRAGON V5 Daily Newspaper`,
uses `python dragon_watchdog.py`, targets this saved local project, runs daily
at 07:00, and is `PAUSED`.  The evaluator output for the current source tree
was:

```json
{
  "status": "READY_FOR_FINAL_LIVE_AUTHORIZATION",
  "allows_new_trial": true,
  "pre_live_checks": {
    "configuration": "PASS",
    "paused_local_scheduler": "PASS",
    "no_current_trial_requiring_review": "PASS"
  }
}
```

Prior failed raw trial evidence remains unmodified and does not count as a
successful receipt.  No provider was invoked while performing this audit.

## Regression coverage

The evaluator has twelve deterministic transition tests covering the ready
state, build-behind/cutover/single-scheduler/provider safety failures, missing
or active/misconfigured scheduler records, a technically valid trial awaiting
human review, and a reviewed trial awaiting human provider promotion.  Existing
acceptance and provider-trial tests remain responsible for receipt hashing,
review binding, publication, and cutover evidence.

## What a passing trial still must do

The provider command may create only hash-addressed trial material.  A response
is insufficient by itself: it must validate research and articles, persist a
`VALIDATED_AWAITING_HUMAN_REVIEW` receipt, preserve raw failure evidence when
validation fails, and receive a real hash-bound human review before anyone may
mark the provider integration as `PASS`.  A later production edition must pass
the independent editorial, fact-check, Arabic, cover, PDF, EPUB, finality, and
remote archive checks.  Cutover remains blocked until the complete acceptance
audit says otherwise.
