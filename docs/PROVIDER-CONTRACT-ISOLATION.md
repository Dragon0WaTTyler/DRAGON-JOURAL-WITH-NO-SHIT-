# Provider contract fault isolation and exact offline comparison

## Baseline and scope

Baseline: `662113abbb2dac395534552b799d33d3cdde4aff`, following `9c1e408`.
The primary evidence is the complete durable bundle
`provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99`.
Its manifest SHA-256 is
`ba2899253f187da1d77acac28210f6d738635b5272945eb8382098fa27497ae8`;
raw response SHA-256 is
`1a9dd26cd2cf9795a09f2daf87d42a1e2a565bd3e3bdb8fb9ba8d141d224039d`.
The original recorded failure and all original bytes remain unchanged.
September 27 primary artifacts are unavailable and exact replay is impossible;
the permanent user-authorized waiver is in `HISTORICAL-ARTIFACT-STATUS.md`.
No September 26 packet replaces them.

The original path was `research -> normalize_research_packet ->
_validate_hard_target_results`. The strict helper iterated every target and
candidate in one call. Rotork's declared INDEPENDENT expectation with an empty
independent ID list raised `HARD_TARGET_DISPOSITION_INVALID`; the exception
rejected the whole packet before materialization. The SERVICE disposition was
a valid explicit no-result with five reported attempts, not silent omission.

## Failure scopes

`dragon/provider_contract.py` applies validation to a private copy of the raw
response before the existing evidence normalization. It reuses the strict
target helper and canonical candidate evidence checks.

| Scope | Examples | Result |
|---|---|---|
| Global | Invalid root/date/version, corrupt source registry, absent section inventory, ambiguous globally duplicated candidate IDs, unidentifiable target registry | Reject packet |
| Target | Missing/duplicate disposition, inconsistent status, missing search attempt | Explicit CONTRACT_VIOLATION; preserve other targets |
| Candidate | Malformed structure/references, mismatched target, declared role without explicit IDs, incompatible roles or origins | Quarantine candidate; preserve valid siblings |

All-invalid CANDIDATES_PRODUCED becomes
`CONTRACT_VIOLATION_NO_VALID_CANDIDATES`. It never becomes a fabricated successful
no-result. A valid explicit `NO_QUALIFYING_CANDIDATE_FOUND` is retained verbatim.
Candidate IDs outside the failing target's desks cannot be erased by a bad
cross-target match. Removed candidates leave both publication and recovery pools.

Every target exposes raw/accepted/rejected counts, raw/effective disposition,
contract status, rejection codes/reasons, and original target records. Raw counts
count returned match entries, including duplicates. Quarantined desk candidates
are also individually recorded even when the provider omitted their target match.

The existing two-candidate ACTIVE desk floor remains. Losing that floor, or
rejecting the selected lead, produces NO_NEWS with valid survivors retained as
RESEARCH_INCOMPLETE recovery candidates. No alternative is silently selected for
publication. Legacy unambiguous evidence normalization remains in its original
path; an explicit hard-target role contradiction is rejected before that path.

## Initial no-result scheduling

A validated empty provider target has no executable candidate opportunity in
epoch zero. Its edition-wide acquisition job is marked
`PROVIDER_NO_RESULT_REQUIRES_RECOVERY_EPOCH`; its actions are deferred until the
existing bounded recovery epoch. The need stays unresolved. Epoch one can plan
normal acquisition again. This avoids consuming an initial SERVICE slot without
disabling recovery or changing budgets, retries, semantic definitions, or evidence
requirements. Existing reservation and fairness code is reused unchanged.

## Exact current-code comparison

From the implementation checkout:

```powershell
python dragon_acceptance_bundle.py compare-contract --bundle <absolute-durable-bundle-path>
```

This verifies every original archived hash before and after replay, uses the exact
raw response, request targeting, timestamp, frozen configuration, and monitoring
inputs, then runs the real normalizer, planners, materializer, and scheduler.
It has no provider invocation, search/retrieval adapter, execution runner,
or editorial/publication entry point. Sources remain PROVIDER_REPORTED;
retrieval/evidence provenance is not fabricated.

Two results must be exactly equal. The comparison is stored outside the original
bundle, under the shared durable `contract-comparisons` directory. Its receipt
binds input manifest/raw hashes, comparison revision, all Dragon Python module
hashes, CLI hash, and both output artifact hashes. Incomplete writes stay explicit;
existing receipts are hash-verified and never overwritten. The Markdown report
lists both raw hard-target candidates and all materialized actions with decisions.
The JSON retains the full normalized packet, raw candidate audit, scheduler inputs,
all actions, selection order, and deferred actions.

`replay` still reproduces original behavior and requires the original revision
and implementation hashes. `compare-contract` intentionally uses the new code;
it does not replace the historical verdict.

## Exact fresh-packet result and limits

| Target | Raw matches | Accepted | Rejected | Effective result |
|---|---:|---:|---:|---|
| ACCOUNTABILITY | 2 | 1 | 1 | CANDIDATES_PRODUCED, PARTIAL |
| SERVICE | 0 | 0 | 0 | NO_QUALIFYING_CANDIDATE_FOUND, PASS |

`inv-itrane` passes the structured target contract independently: PRIMARY `s1`,
INDEPENDENT `s2`, exact artifact `s1`. `inv-rotork` remains rejected with
`INVALID_EVIDENCE_ROLE_LINKAGE`: expected INDEPENDENT, explicit independent IDs
empty; PRIMARY/exact `s3`. No IDs, facts, quotations, or source access are invented.

Nine jobs materialize 31 actions. The scheduler selects eight and defers 23.
ACCOUNTABILITY reserves `ACT-156391587BBA` (PRIMARY) and `ACT-EBB9846FF233`
(INDEPENDENT), both FETCH_URL for `investigations:inv-itrane`.
SERVICE has zero executable initial actions and consumes zero reservations.
The existing round cap is eight, reserved capacity two, remaining normal
allocation capacity six, discovery reservation one, budget increase false.
Both hard deficits remain open; selected actions are not executed.

This proves contract isolation, deterministic lineage, and bounded allocation.
It does not prove live URL availability, actual source independence, current-event
semantic/temporal qualification, deficit closure, or publication eligibility.
Those still require real retrieval in a separately authorized future trial.
The semantic, temporal, primary, independent-origin, source-family, exact-provenance,
provider-call, budget, and publication gates retain their existing authority.

## Regression coverage

`tests/test_v5_contract_isolation.py` covers candidate/target isolation, all-invalid
outcomes, global corruption, role/origin contradictions, malformed target status,
cross-target references, selected-lead protection, portable fixture scheduling,
bounded recovery, exact archived replay, deterministic equality, network/provider
tripwires, receipt reuse, and tamper/overwrite rejection. The exact bundle case
skips only on checkouts lacking that task's primary archive; it runs on this PC.
Existing archive and editorial-provider tests now assert quarantine for local
faults and retain global rejection/publication blocking checks.

Run the focused provider/evidence/routing/archive tests and full `python -m pytest -q`
before accepting the patch. A green offline suite does not authorize a live call.
