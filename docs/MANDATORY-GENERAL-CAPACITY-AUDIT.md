# Mandatory acquisition and GENERAL capacity audit

Baseline: `133dce654ee3153d7f5368bfec9eb31f9b083ebd`, resolved from the cached
canonical `origin/main`, independently of the stale local `main` branch.
Sealed run: `provider-research-acceptance-22039760-28ca-4fe8-9165-177497820e5a`.
Manifest SHA-256: `5bd3565ccab39950ca2d78370add44546d578d252461c55dd16e788deea91e81`.
The audit uses zero provider calls and zero network calls. No archived record is
rewritten. The original implementation's deterministic bundle replay passes.

## Chronological native execution

This is the persisted execution order, not the scheduler's interleaved list.
The dispatcher groups selected actions by job while retaining job order.

| Position | Epoch | Action ID | Lane | Classification | Mandatory at execution |
|---:|---:|---|---|---|---|
| 1 | 0 | ACT-D60E571DCD46 | ACCOUNTABILITY | ACCOUNTABILITY_CORE | yes |
| 2 | 0 | ACT-6591CD10A995 | ACCOUNTABILITY | ACCOUNTABILITY_CORE | yes |
| 3 | 0 | ACT-19D63FB116C6 | ACCOUNTABILITY | ACCOUNTABILITY_CORE | yes |
| 4 | 0 | ACT-B88184D34C48 | ACCOUNTABILITY | ACCOUNTABILITY_CORE | yes |
| 5 | 0 | ACT-CD62F672E326 | SERVICE | SERVICE_CORE | yes |
| 6 | 0 | ACT-64F4841EE98A | SERVICE | SERVICE_CORE | yes |
| 7 | 0 | ACT-A855D745E2A7 | SERVICE | SERVICE_CORE | yes |
| 8 | 0 | ACT-FFFF7FA9C979 | GENERAL | GENERAL | no |
| 9 | 1 | ACT-A81B1FC13AF9 | SERVICE | SERVICE_CORE | yes |
| 10 | 1 | ACT-81FF55D55DD2 | ACCOUNTABILITY | ACCOUNTABILITY_ACTIVE_PATH | yes |
| 11 | 1 | ACT-1098B8B5CD76 | SERVICE | SERVICE_ACTIVE_PATH | yes |
| 12 | 1 | ACT-4850C3D7DEF5 | SERVICE | SERVICE_ACTIVE_PATH | yes |

Neither OPTIONAL_HARD nor an inactive FALLBACK executed. An originally deferred
PDF became the selected active path in epoch 1; classification above refers to
its state at execution, not its prior state.

At GENERAL admission, SERVICE's alternate search was already materialized,
mandatory, unexecuted, and deferred by the eight-action round selection. Both
lanes' candidate acquisition had yet to be selected: the epoch-0 acquisition
receipt's `selected` mapping is empty. The Court of Accounts PDF and Morocco
election-page alternatives had already been discovered. They were recorded
alternatives, not simultaneous mandatory paths.

Immediately before GENERAL, nine global slots remained. The receipt's core-only
minimum was one, derived by subtracting the seven completed core IDs from the
eight core IDs. After GENERAL, eight global slots remained. There is no persisted
per-action minimum snapshot; the end-of-epoch receipt confirms minimum one and
remaining execution capacity eight. The scheduler's earlier minimum nine
included eight core actions plus its one GENERAL reservation. GENERAL's own
admission test excluded its reservation from the required minimum.

## Minimum evolution and foreseeability

| Boundary | Previous minimum | New minimum | Status and cause |
|---|---:|---:|---|
| Epoch-0 selection | — | 9 | persisted: eight core actions plus GENERAL |
| Each of the first seven core completions | 8 through 2 | 7 through 1 | derived hard-only minimum; discovered alternatives remained unselected |
| GENERAL completion | 1 | 1 | derived: no mandatory obligation completed |
| Epoch-0 receipt | — | 1 | persisted: SERVICE alternate search remains |
| Epoch-1 selection | 1 | 7 | persisted: core 1 + selected audit artifact and unresolved independence reservation 3 + selected SERVICE exact pages 3 |
| SERVICE alternate search | 7 | 6 | derived: captured RSS_NO_MATCHES completes the last core step, creates no route |
| Audit PDF completion and failure | 6 | 5 | derived: temporal rejection promotes UK PRIMARY/INDEPENDENT exact pair; rejected route's abstract reservations cease to be active |
| Ameli completion and selected child registration | 5 | 5 | derived: one fetch completes and a concrete child inspection is registered |
| Vidal completion and failure | 5 | 5 | derived: temporal rejection promotes Morocco SERVICE page + independent search/fetch reservation |
| Final receipt | — | 5 | persisted: remaining capacity four, structural blocker |

Sub-action transient minima were not saved. The derived rows apply the captured
completion, rejection, registration and promotion events using `HardAcquisition`;
they do not pretend that per-action snapshots existed.

Foreseeable acquisition reservations follow the existing implementation:
an unknown claim topology reserves PRIMARY plus independent acquisition; a
native PRIMARY route without an independent URL needs an independent search
and an exact-result fetch. A selected role query similarly reserves its result
inspection. Provider exact-role URLs were available before GENERAL, but their
selection was deferred until the discovery epoch finished.

The concrete fallback promotions are contingent. The audit PDF's temporal
failure causes the UK pair to become mandatory. The Vidal temporal failure
causes the Morocco SERVICE page and its unknown-role reservation to replace
the failed SERVICE path. Those inspection results were not known at GENERAL
admission. The contracts do not provide a finite upper bound for every later
failure and fallback, so currently fitting reservations alone cannot guarantee
that an irreversible early optional action is safe.

| Obligation active after GENERAL | Classification | What was knowable before GENERAL |
|---|---|---|
| ACT-A81B1FC13AF9, SERVICE alternate search | FORESEEABLE_RESERVATION | concrete mandatory core action was already planned |
| ACT-81FF55D55DD2, selected audit PDF inspection | FORESEEABLE_RESERVATION | exact link discovered during canonical navigation; one active PRIMARY route still needed inspection |
| ACT-1098B8B5CD76, ACT-4850C3D7DEF5 and ACT-9186801BE073, selected SERVICE exact pages | FORESEEABLE_RESERVATION | exact proposed URLs and role assignments existed; active PRIMARY/independent acquisition was still outstanding |
| ACT-E12AB78F5D21, selected Ameli child | CONTINGENT_EXPANSION | concrete child obligation arose from inspection of the parent, not from a pre-existing mandatory request |
| ACT-A5A1E5E2CEFD and ACT-198651D2B943, promoted UK pair | CONTINGENT_EXPANSION | alternative URLs existed; they became mandatory only after the audit route failed |
| ACT-79CEE40D4902, promoted Morocco SERVICE page | CONTINGENT_EXPANSION | alternative URL existed; it became mandatory only after Vidal's temporal failure |
| SERVICE independent search and exact-result inspection, no IDs yet | FORESEEABLE_RESERVATION on the newly active native path | the existing role contract requires these slots for unknown topology; their activation on this particular fallback remains contingent on the earlier path failure |

Foreseeability reserves work for one active path, not all recorded alternatives.

## Counterfactual boundary

Keep every captured search, candidate order, qualification result and artifact
unchanged. Defer GENERAL and put the already-scheduled SERVICE alternate search
in epoch 0's eighth slot. Its captured result is `RSS_NO_MATCHES`, with no new
candidate, so the epoch-1 selected paths remain the same. Epoch 1 then executes
the three captured exact fetches instead of those fetches plus the core search.

The transition replay reproduces the actual final selection and minimum five.
Actual capacity is four; counterfactual capacity is five. The immediate recorded
capacity refusal disappears with no budget or policy change:

`8 core + 3 captured selected inspections + 5 remaining acquisition minimum = 16`.

This answers **YES for the recorded acquisition minimum**, and **PARTIALLY for
complete acquisition**. Five is a minimum, not the final execution length.
The three explicit unexecuted fetches are:

* `ACT-A5A1E5E2CEFD`: UK government PRIMARY page;
* `ACT-198651D2B943`: AOL/Reuters independent page;
* `ACT-79CEE40D4902`: Morocco SERVICE page.

The other two slots reserve a SERVICE independent search and exact-result
inspection. None of these requests has a captured native retrieval result.
An executable counterfactual must stop there, rather than manufacture empty
results or assume successful inspection, no further fallback, or PRIMARY-only
policy relaxation. The audit does not prove accepted evidence, verified absence,
complete acquisition, or a legitimate hard path necessarily requiring more
than sixteen actions. More-than-sixteen and successful-sixteen are both
unproven beyond the captured boundary.

## Correction and contract

Root cause at the captured capacity boundary:
`GENERAL_CAPACITY_PREEMPTION_DEFECT`. The protected GENERAL reservation displaced
known mandatory core work, and its executed slot makes the same final minimum
fail by one. This conclusion is narrower than claiming successful hard closure.

For new runs, GENERAL is best-effort after mandatory acquisition settles:

* schedule all mandatory core work before adding a GENERAL root;
* count only hard acquisition in the mandatory minimum;
* retain GENERAL as a selected tail action or deferred opportunity, preserving
  its ID and original job/counters into the existing second epoch;
* dispatch GENERAL only after the core and selected path's acquisition requests
  have no remaining work and no unselected discovery frontier remains;
* let dynamic mandatory actions consume a pending GENERAL slot;
* record `GENERAL_PREEMPTED_BY_MANDATORY_ACQUISITION` if hard work leaves no safe
  admission point, without converting that disposition into research failure.

This chooses the task's Contract B. No fixed extra slot is reserved. Optional
hard lane behavior and optional-child protection remain bounded. The unchanged
evidence evaluator still determines finality: settled acquisition is not
evidence acceptance. Historical runs retain the earlier protected-GENERAL
contract described in `BOUNDED-HARD-ACQUISITION.md`.

## Validation and delivery

Offline regressions include a synthetic sixteen-action hard protocol with
GENERAL deferred, spare-capacity late GENERAL execution, foreseeable role
reservation, captured contingent promotion, independent lane state, cumulative
job allowances, no repeated action, optional behavior and fail-closed finality.
The sealed live projection preserves only action topology, URLs, role metadata,
captured failure codes and hashes; raw provider response and source text stay
host-local.

The original sealed run is replayed from its exact implementation checkout.
The revised projection separately replays the captured capacity transitions;
it intentionally does not assert equality with the old GENERAL allocation.
Production automation remains paused, all configuration and evidence policy
files remain byte-identical, and no live acceptance occurs here.

GitHub push, PR, hosted CI, Codex review and remote read-back require network
access. They are deferred under this task's explicit zero-network requirement.
Local test evidence and a focused commit are reviewable; this change awaits
normal remote review/merge before a separately authorized fresh live acceptance.

Validation completed: focused suite **213 passed**; full suite **1056 passed,
2 skipped**. Both used a socket connection blocker and recorded zero connection
attempts. Full-suite fixture runs isolated their local browser binding inside
the test process: the host's enabled browser proof correctly rejected the edited
executor hash during the first run. Its runtime configuration and receipt were
not changed. The original sealed replay independently intercepted provider and
network entry points and recorded zero calls. Config, targeting, evidence and
finality source comparisons against the canonical commit are clean.

The browser readiness receipt binds the executor implementation hash. A future
merged correction needs a fresh supported browser readiness proof before live
acceptance; offline tests do not refresh or bypass that production gate.
