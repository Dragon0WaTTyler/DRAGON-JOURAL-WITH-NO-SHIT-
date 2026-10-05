# Hard-lane offline audit

This audit follows the objective attached on October 4, 2026. No live provider
call, network retrieval, editorial stage, publication, delivery, or scheduler
activation is authorized by that objective.

## Baseline and historical evidence

The available implementation worktree is `codex/hard-lane-yield`, initially at
`0e87e8623fc7ca732fd0b1db09dc8b59a42e9d34`. The original provider-targeting
baseline is `b8b4ffe924257831355823fb96eed62f185be9e8`. Commit
`e2cffd6ac5b2d03bd33940175fbbdf2f5a3208e3` already implemented structured
hard-target dispositions and bounded hard-lane reservation. Later commits
preserve acceptance bundles and remove unsupported output-schema composition.

`SEP27_EXACT_REPLAY = UNAVAILABLE_MISSING_PRIMARY_ARTIFACTS`

The original September 27 run directory and raw provider packet are missing
from the available worktrees and archive. The supplied account of that trial
does not establish which provider/normalization step lost SERVICE candidates,
nor the exact scheduler inputs and displaced actions. An exact historical trace
and before/after replay remain unavailable. Historical artifacts must not be
reconstructed to fill this gap.

Source inspection establishes two defects in the original baseline:

- The research schema and normalizer permitted omission of a requested hard
  target's structured result. Zero SERVICE candidates could pass without an
  explicit search attempt or no-result disposition. This proves a contract
  defect; it does not prove whether the historical provider ignored SERVICE,
  misclassified a candidate, or failed to find a qualifying event.
- Candidate exact URLs inherited ordinary context priority. Under P0/P1/P2
  pressure, the scheduler excluded P3 actions except a single general-discovery
  reservation selected by deterministic job/action ordering. The original
  scheduler had no per-hard-lane exact-artifact reservation. A fixture reproduces
  starvation of an accountability pair; the missing historical inputs prevent
  identification of its precise September 27 scheduling decision.

## Existing provider and scheduling contract

`dragon/provider_targeting.py` projects canonical semantic definitions,
exclusions, dates, and first-party SERVICE artifact preferences.
`scripts/codex_editorial_provider.py` requires structured hard-target results.
`dragon/providers.py` validates one result per requested hard target, search
intent and attempts, candidate references, semantic/current-event rationale,
expected roles, exact source references, and a reason when no qualifying
candidate was found. Missing results fail with
`HARD_TARGET_DISPOSITION_MISSING`; the diagnostic records
`MISSING_PROVIDER_DISPOSITION`, never an invented unsuccessful search.

`dragon/deep_research.py` attaches a live unresolved deficit and expected source
role to selected provider exact-source lineage. It does not grant evidence
status. `dragon/deep_research_executor.py` first reserves one available action
per active hard lane, prefers exact provider artifacts and PRIMARY suggestions,
retains a general-discovery opportunity, and then considers a matching
primary/independent pair inside the same cap. Remaining capacity uses the
existing priority/fairness pass. `dragon/pipeline.py` persists scheduling,
execution, closure, and recovery telemetry by epoch.

## Additional defects reproduced and fixed in this audit

Two new regression tests failed before the corrections:

1. A recovery job whose attempt allowance was exhausted fell back to ordinary
   candidate/context queries while retaining its hard-lane label.
2. A job whose fetch counter reached its existing limit could still receive a
   reserved exact fetch that the executor would skip.

The planner now returns no actions for an exhausted recovery job. The scheduler
checks existing search/fetch counters before allocating execution capacity;
unavailable actions remain visible with
`JOB_ACTION_ALLOWANCE_EXHAUSTED`. These checks retain bounded pivot allowances.
They do not raise any limit or change evidence qualification.

Reservation telemetry now counts both members of a reserved pair, records their
action IDs, and subtracts both from remaining general capacity.

## Deterministic fixture comparison

The comparison executes the scheduler definitions from Git baseline `b8b4ffe`
and the current scheduler against identical fictional jobs and configuration.
It is explicitly `SYNTHETIC_FIXTURE_COMPARISON_NOT_SEP27_REPLAY`. Both schedulers
select **8 actions under cap 8**.

The corrected scheduler selects:

- `ACT-41AA691D2B15`: PRIMARY suggestion, exact fixture accountability report;
- `ACT-65E84790E69A`: INDEPENDENT suggestion, same candidate's fixture report;
- the previous general-discovery action;
- world/breadth and distinct-event research;
- additional accountability research under normal fairness.

The two displaced fixture actions are:

- `ACT-E8E4553727A2`: `DISTINCT_EVENT_RELAXED`, an additional distinct-event query;
- `ACT-F2937C786654`: `FUNCTION_ACCOUNTABILITY_CANONICAL_INSTITUTION`, an
  additional accountability query.

The initial distinct-event opportunity and world research survive. The pair
reserves 2 of 8 existing slots, leaving 6 for the general/fairness pass. A separate
test gives both ACCOUNTABILITY and SERVICE an opportunity plus general discovery
inside cap 8. Closed/exhausted/no-executable-action cases reserve zero slots.

The provider-free proof is retained outside the worktree under the shared Git
directory at
`dragon/research-acceptance/offline-audits/hard-lane-6fa6fc2e-5d64-4639-b543-44a81d15764c/`.
It includes its executable `run-proof.py`, fictional jobs/configuration,
baseline and current schedules, static-adapter execution results, normalized
dispositions, omission diagnostics, and a SHA-256 inventory in `receipt.json`.
Both reserved exact fetches executed; failed fixture responses created zero
source evidence. The receipt binds the working source hashes at execution,
before this audit's milestone commit, and records zero provider/network calls.

`config/deep-research.yaml` is byte-identical to `b8b4ffe`; SHA-256:
`a16adbf4c4fba960be8fdd35c7e405124ad0971e1da2b7be1466e7a6f9b77051`.
Round cap, per-job search/fetch limits, follow-up limits, observation limits, and
recovery allowances are unchanged.

## Checks and boundaries

The initial focused suite passed 174 tests. Five added regressions cover next
epoch closure, exhausted need materialization, exhausted job fallback,
unavailable fetch capacity, and failed exact-fetch lineage/budget. The final
focused suite passed 179 tests. The pair test additionally checks accurate
reservation telemetry. The final full suite passed **810 tests**, with **2
skips** and **0 failures**, in 207.85 seconds. Both skips are
`tests/test_automatic_publication.py` cases requiring installed WeasyPrint native
libraries; they are enabled in Linux CI.

Existing regression coverage exercises explicit no-SERVICE-result preservation,
omission rejection, generic candidate mismatch, both-lane reservation, unsafe
URLs, retrieval failures, semantic/current-event validity, required primary
evidence, independent origins, same-origin rejection, and valid event bundles.

No semantic, temporal, primary, independent-origin, source-family, exact-page
provenance, publication, or provider-call gate is weakened. Provider role labels
remain unverified suggestions. New regression fixtures invoke zero providers
and use static adapters.

The October 4 failed live bundle remains incomplete and unchanged. Its existing
artifact hashes verify, and its manifest SHA-256 remains
`d5e73b7f34f6d27c967a9f18d5057048f6ca2d5233bbfcaf95746a6c0f31c44f`.
This task adds zero provider invocations and cannot convert that earlier failed
trial into live acceptance evidence.

The remaining historical acceptance requirement is restoration of the original
September 27 packet and scheduler inputs. Another provider trial requires
separate explicit authorization after review of the offline evidence.
