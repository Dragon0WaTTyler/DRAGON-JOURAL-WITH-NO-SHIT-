# Scheduler failure

## Symptoms
The sole Codex local automation does not start the watchdog, starts twice, or misses the target deadline.
## Failure codes
`SCHEDULER_NOT_INSTALLED`, `DUPLICATE_RUN`, `WATCHDOG_STALE_RUN`.
## Likely causes
Paused/missing Codex automation, wrong project binding, stale lock, or changed canonical command.
## Automatic actions
The watchdog captures state and resumes only after proving no live owner exists.
## Fallback order
Codex automation retry; watchdog resume; one manual `dragon_watchdog.py` run.
## Data never to overwrite
Completed dated editions, live locks, and valid stage checkpoints.
## Retry limit
One scheduler invocation; stage retry limits remain authoritative.
## Stop condition
Stop on a live owner, ambiguous lock ownership, or runtime-fingerprint mismatch.
## Resume behavior
Use the same date and `--resume`; never create a second schedule.
## Manual recovery
Exceptional only: inspect the Codex automation and state before one manual watchdog invocation.
