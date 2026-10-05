# Verified no-event closure and research finality acceptance

Audit date: 2026-10-05. Implementation acceptance is complete. The October 4
evidence replay truthfully remains blocked for production. No live provider,
network retrieval, article generation, cover, edition rendering, publication,
scheduler activation or delivery was performed for this objective. Existing
regression tests use their established fixtures and synthetic paths.

## A. Baseline

- Starting commit: `db21fc01ee512a131e46c7d546b25bc13f4bec28`.
- Worktree: `C:\Users\walid\.codex\worktrees\contract-fault-isolation\dragon journal with no shit`.
- Branch: `codex/verified-no-event-finality`.
- Recorded baseline regression: **871 passed, 2 skipped**, 247.62 seconds.
- Accepted Phase 2 technical research acceptance remains PASS. This is an
  audit of its downstream finality, not a rewrite of its historical verdict.

The sealed inputs are preserved under the primary repository's
`.git/dragon/research-acceptance`, outside disposable worktree state:

| Bundle | Artifacts | Manifest SHA-256 |
| --- | ---: | --- |
| `provider-research-acceptance-f1bd0998-d792-4d28-851c-b1c60bfa1f99` | 67 | `ba2899253f187da1d77acac28210f6d738635b5272945eb8382098fa27497ae8` |
| `retrieval-acceptance-1f48cf07-184b-4cad-a05a-d9a4386ff17d` | 144 | `29ba62deecb661bc47db670660bf8ee04648cbf9ba53b5714846ca63b34bc7dc` |
| `retrieval-evidence-review-5333ed4a-38da-4fdd-93e8-1b74baecc416` | 93 | `dd125ecaa8f8634fe100facc8050ca57611ff31ff0e5f4cc1a059836e8c23d8f` |

The third bundle supplies the accepted corrected provenance decisions while
retaining identical original action request/response packets. All 16 dispatch
requests match the original trial; only post-response `actual_information_gain`
is excluded from the request comparison. No response bytes are excluded.

## B. Existing ambiguity

At baseline, `dragon/research_recovery.py:build_recovery_plan` used remaining
event/evidence needs to derive `PASS`, `RECOVERY_REQUIRED` or
`RESEARCH_INSUFFICIENT`; `article_generation_allowed` meant `not needs`.
`validate_recovery_plan` validated that relationship. These fields did not
represent successful bounded research with no qualifying event separately
from incomplete research. Exhausting retries did not prove absence.

The baseline combined ACCOUNTABILITY/SERVICE event metric counted a union of
eligible events. It did not establish independent research completion for each
requested hard lane. Two ACCOUNTABILITY events could meet that union minimum
while SERVICE still needed research.

`dragon/providers.py:_validate_article_research` also enforced the inherited
ACCOUNTABILITY/SERVICE selected-section floor, without a proof-bound absence
state. It now recognizes verified absence while retaining the edition's other
coverage, active-story and word floors. Existing event metrics retain their
old meaning; new research-completion fields are explicit.

## C. State model

| State | Research treatment |
| --- | --- |
| `VALIDATED_EVENT` | Acceptable terminal research state; real event passed existing evidence gates |
| `VERIFIED_NO_QUALIFYING_EVENT` | Acceptable terminal research state; strict bounded negative closure, zero invented events |
| `BLOCKED_TECHNICAL_FAILURE` | Blocks handoff |
| `BLOCKED_CONTRACT_FAILURE` | Blocks handoff |
| `BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH` | Blocks handoff; reason `SEARCH_CUT_SHORT_BY_CAPACITY` |
| `UNRESOLVED` | Blocks handoff; reason `UNRESOLVED_SEARCH_NOT_EXHAUSTED` |

Deterministic precedence is unresolved technical failure, contract failure,
validated event, truncated required capacity, strict negative closure, then
unresolved proof. A valid event can close research without performing otherwise
unused discovery, but unresolved technical/contract failures still take
precedence. A no-event result requires every negative-closure check.

## D. Negative-closure contract

All eleven machine-observable conditions must pass for each mandatory lane:

1. Exactly one actual hard target was requested for this research date.
2. Exactly one valid explicit provider disposition is preserved.
3. Structured provider search attempts include query and purpose. Their
   provenance is labelled provider-reported, not independently observed.
4. Target normalization passed, agrees with surviving candidates, and has no
   target error. Candidate quarantine is preserved separately.
5. The native bounded acquisition/recovery ladder completed, including every
   core strategy, selected exact request and required concrete follow-up;
   requests, observations and round execution ledgers agree.
6. No qualifying or potentially qualifying candidate/lead remains unevaluated.
7. No unresolved required technical failure remains.
8. No unresolved target, request identity or protocol contract failure remains.
9. Capacity was available for every required search; deferred core actions
   cannot be called successful exhaustion.
10. No qualifying validated evidence bundle exists.
11. A valid closure timestamp is recorded.

The proof includes research date/window, source universe, queries/routes,
attempts, action identities/counts, recovery epochs, caps, response observations,
content hashes, quarantine, rejection reasons, pending leads and limitations.
Packet/input/decision hashes bind it; editorial preflight rebuilds the decision.

The scope is the native configured acquisition ladder and selected exact
follow-ups. Broad route/alternate-channel expansions after empty results are
contingent on spare capacity, explicitly audited as optional deferrals. They
cannot replace core strategies. Concrete-event and required-role follow-ups
remain mandatory. An identical exact acquisition may reuse the same lane/date/
URL's hash-bound artifact, recorded as reuse rather than execution. Searches
cannot substitute for another strategy or language/channel.

Verified absence means no qualifying event was found within this recorded
protocol, universe, window and resources. It does not claim universal absence.

## E. SERVICE replay

- Actual hard target present; disposition `NO_QUALIFYING_CANDIDATE_FOUND`.
- **Five** provider-reported attempts; zero raw/accepted candidates, no target
  normalization fault or schema/provider failure.
- Epoch 0 had no executable SERVICE action and no reservation.
- Epoch 1 executed **four native core actions plus four admitted exact
  follow-ups**: required 8, executed 8, missing 0, reused 0.
- Empty SearXNG/RSS responses were successful empty results.
- Required action `ACT-A33C1006860B`, Office des Changes SMART route
  `https://www.oc.gov.ma/fr/e-services/smart`, returned HTTP 200 but no static
  page content. Observation `OBS-CF9F4F35BE6E` records
  `SOURCE_DYNAMIC_ROUTE_REQUIRED`: static extraction failed on a script-driven
  page. HTTP success did not establish usable source acquisition.
- **Eight uninspected discovery leads** remain pending. Their exact identities
  are saved in `finality/decision.json` and the final audit receipt.
- No qualifying SERVICE evidence bundle/event was validated.

Final state: **`BLOCKED_TECHNICAL_FAILURE`**, reason
`REQUIRED_RESEARCH_FAILED`. Missing conditions are
`no_unresolved_technical_failure` and `no_qualifying_candidate_survived`.
Therefore `SERVICE_NEGATIVE_CLOSURE=false`. The requested audit's premise that
no retrieval failure prevented completion is contradicted by the preserved
page extraction evidence. No outcome was forced.

## F. ACCOUNTABILITY replay

- Disposition `CANDIDATES_PRODUCED`; **four** provider-reported attempts.
  Two raw candidates yielded one accepted Itrane candidate and one isolated
  contract quarantine (Rotork). Target status PARTIAL has no target fault.
- Itrane exact requests `ACT-156391587BBA` and `ACT-EBB9846FF233` succeeded.
  Observations `OBS-35A1CFFC91CF` and `OBS-4DF05A5768BE` preserve the actual
  first-party concentration notification and the secondary copied summary.
- Captured text describes a proposed concentration transaction, not a
  qualifying audit, sanction, enforcement or oversight action. Canonical
  ACCOUNTABILITY semantics failed. PRIMARY for a qualifying accountability
  event was not met; original independent corroboration was not established.
- Native bounded recovery planned **four core strategies**. Only
  `ACT-A692E56FD7B2`, a Cour des comptes route-scoped search, executed and
  returned `SEARXNG_NO_MATCHES`.
- Three required core actions never executed:
  `ACT-1EB65BE1C83E`, `ACT-4D0BEADD0AFD`, `ACT-5C810EDC1C10`.
  No ACCOUNTABILITY epoch 1 job completed those obligations.
- Totals: required 6 (two exact requests + four core searches), executed 3,
  missing 3, reused 0. An additional deferred broad route expansion
  `ACT-19A4910B73C9` is separately recorded as optional, not substituted for
  any of the three missing core searches.
- No unresolved technical failure, pending event, or validated event remained
  in this lane. Correctly rejecting Itrane is insufficient to establish absence.

Final state: **`BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH`**, reason
`SEARCH_CUT_SHORT_BY_CAPACITY`. Missing conditions are
`bounded_acquisition_recovery_completed` and
`required_search_capacity_available`. Therefore
`ACCOUNTABILITY_NEGATIVE_CLOSURE=false`.

## G. Combined coverage

- Mandatory hard-lane research coverage: **incomplete**.
- Validated hard-lane event coverage: **0**, ACCOUNTABILITY 0, SERVICE 0.
- SERVICE has one required technical failure and eight pending discovery leads.
- ACCOUNTABILITY has three unexecuted core recovery strategies.
- Four existing non-hard research needs remain: `BREADTH:morocco_breadth:1`,
  `BREADTH:morocco_breadth:2`, `BREADTH:world_breadth:1`,
  `BREADTH:reader_life:1`.

`combined_research_coverage_complete` accepts validated event or verified
no-event independently per mandatory lane. `combined_event_coverage` counts
only genuine validated events. The old `editorial_function_coverage` and
historical `COMBINED_COVERAGE_SATISFIED` meanings remain unchanged;
`event_coverage_needs` retains the original event deficits.

## H. Finality behavior

| Lane state | Can support editorial handoff? |
| --- | --- |
| Event validated | Yes, when every mandatory lane and all other recovery needs are complete |
| Verified no-event | Yes, under the same global completion condition; explicit absence omits unsupported stories |
| Technical failure | No |
| Contract failure | No |
| Incomplete search / required budget truncation | No |

Negative closure supplies `OMIT_UNSUPPORTED_STORY`, uses the existing
`NO_NEWS`/`SKIP` editorial shape and an Arabic reason, and receives no full-story
word budget. It cannot count toward active-story floors or become an active
article. The original research packet is retained. No older event, background
or generic criticism is selected as a replacement.

The production recovery fixture proves that both lanes can close negatively
after their full native ladders execute. Production article preflight still
requires the inherited active-story, total-word and other coverage floors.
Research completion alone never establishes publication completion.

## I. Tests

| Scope | Passed | Skipped | Failed | Time |
| --- | ---: | ---: | ---: | ---: |
| New finality tests | 32 | 0 | 0 | 7.00 s |
| Relevant regression | 175 | 0 | 0 | 54.31 s |
| Full regression | 903 | 2 | 0 | 259.71 s |

The two full-suite skips are the existing Windows WeasyPrint native-library
cases at `tests/test_automatic_publication.py:321` and `:327`, also skipped at
baseline. They remain enabled in Linux CI. No final failing test is hidden.
The real October 4 preserved-bundle test ran and passed on this checkout.

All ten requested cases are covered: valid event; explicit no-result and
completed recovery; omitted target; provider/schema failure; rejected candidate
with complete recovery; candidate without recovery; infrastructure failure;
capacity truncation; mixed positive/negative lanes; all lanes negative without
invented events. Additional coverage checks missing actual request receipts,
closure timestamps, proof tampering, packet changes, other breadth/evidence
needs, strategy substitution, duplicate event placement, required dynamic
fetches, optional expansion auditing, failure resolution chronology, editorial
absence and the production recovery stage.

Sealed replay PASS: new bundle
`research-finality-review-c63490b0-056d-42fb-a51f-3a547e08bf4f`, 43 artifacts,
manifest SHA-256
`c8cccf8821554738f9625f424b44201b479d65f09aea1b0bf35f2f4190e81e3a`.
Input canonical digest:
`b23ac49c85ca3092ef680815dd179e2c0482738defa1d2d881ce4aa0e3d9c77d`.
Decision canonical digest:
`f63489c2a1ecb152eefd148abf97f29df3b96b7aa88bec48cf10d0c1184d24c9`.
The derivative retains exact provider request/response bytes, scheduler states,
execution packets, configuration, lineage and decisions. It was evaluated
twice, sealed and immediately replayed, then independently audited/replayed
again under provider/network call guards. All parent manifests were verified
before and after. Provider calls 0; network calls 0.

## J. Gate preservation

Existing semantic, temporal, PRIMARY, support, exact-page provenance,
independent-origin and source-family requirements remain authoritative. No
candidate is promoted because of hard-lane membership. The new closure module
consumes these gates and adds proof checks; it does not relax them.

Provider schema, research invocation, hard-target prompt, candidate/target
contract isolation, exact URL routing, reservation, retrieval adapters and
durable archive implementation are unchanged. Provider changes are confined to
downstream editorial preflight/absence compatibility. Recovery adds independent
mandatory-lane context and explicit completion semantics.

Original round caps remain **8 + 8 = 16 actions**, all sixteen requests and
responses retained, no added epoch or budget. No scheduler or config was edited.
No fact-check, Arabic QA, canonical-cover, PDF, EPUB, final QA, historical
publication finality, archive/delivery or cutover gate was relaxed. V4 schedules
and historical outputs remain untouched.

## K. Replay verdicts

```json
{
  "SERVICE_NEGATIVE_CLOSURE": false,
  "ACCOUNTABILITY_NEGATIVE_CLOSURE": false,
  "COMBINED_RESEARCH_COVERAGE_COMPLETE": false,
  "COMBINED_EVENT_COVERAGE": {
    "event_ids": [],
    "count": 0,
    "by_lane": {"ACCOUNTABILITY": [], "SERVICE": []}
  },
  "RESEARCH_FINALITY": "BLOCKED",
  "EDITORIAL_HANDOFF_ELIGIBLE": false
}
```

## L. Remaining blocker

The next production stage is blocked by SERVICE's unresolved script-driven
exact acquisition and eight unevaluated leads, ACCOUNTABILITY's three missing
native core searches, and the four recorded non-hard breadth needs. Clearing
those blockers requires new appropriately authorized production evidence and
bounded execution; this offline objective cannot create missing historical
requests or responses. No further live operation is implied by this report.

September 27 remains permanently recorded as:
`SEP27_PRIMARY_ARTIFACTS=UNAVAILABLE`, `SEP27_EXACT_REPLAY=NOT_POSSIBLE`,
`HISTORICAL_REPLAY_WAIVED_DUE_TO_MISSING_PRIMARY_ARTIFACTS`.
No reconstruction, September 26 substitution, or renewed artifact request was
made. New October 4 primary evidence is the authoritative preserved replay.

## M. Git state

Implementation milestone:
`b15cc2171922345febb4120fb4144c9983ddc8ad`,
`feat(research): distinguish verified absence from failed or incomplete research`.
Its full regression passed before the documentation milestone.

| Changed file | Responsibility |
| --- | --- |
| `dragon/research_finality.py` | States, bounded proof, event/absence distinction, deterministic validation |
| `dragon/research_finality_acceptance.py` | Exact offline parent verification, derivative preservation and replay |
| `dragon_research_finality.py` | Offline review/replay CLI |
| `dragon/research_recovery.py` | Independent hard research obligations and completion compatibility |
| `dragon/pipeline.py` | Actual targeting receipt, recovery proof checkpoint, editorial validation |
| `dragon/providers.py` | Editorial preflight and truthful absence handling |
| `tests/test_v5_research_finality.py` | Required and additional regression fixtures |
| `SPEC-v5.md` | Authoritative research-finality contract |
| `docs/RESEARCH-FINALITY.md` | Protocol and operating documentation |
| `docs/RESEARCH-FINALITY-ACCEPTANCE.md` | This acceptance report and requirement audit |

The implementation milestone changed nine files, 1,233 insertions and 13
deletions. This report is a separate rollback-safe documentation milestone;
its exact commit is recorded in the durable final audit after committing.
`git diff --check` passes. Tracked worktree status is clean after both commits;
the accepted `daily-runs/2026-10-04/` tree remains untracked and unchanged.
The primary checkout remains at `cd95120d79c3a760a70f894575760c903182e920`
with the user's pre-existing SearXNG script edits, backup and September run
directories unchanged.

Final archive verification covered all **347** sealed artifacts across the
three inputs and the derivative. Additionally, all **29** original provider
source artifacts and **106** original retrieval source artifacts matched their
sealed hashes. No historical bundle, test report or local trial file was
rewritten. Audit receipts/report copies are separate files under
`.git/dragon/research-acceptance/validation-reports/`.

### Requirement audit

| Objective clause | Acceptance evidence |
| --- | --- |
| 1. Distinguish failed research from successful absence | Six-state proof replaces ambiguity; separate research/event fields |
| 2. Strict terminal no-event closure | Eleven deterministic conditions; completed native protocol fixture |
| 3. State model | Six named states and precedence; failure/budget/unresolved tests |
| 4. Validated event gates | Existing policy/functions/provenance consumed; valid/failed-gate tests |
| 5. Strict no-event proof | Request, disposition, attempts, normalization, protocol, candidates, failures, capacity, bundle, timestamp |
| 6. Epistemic limitation | Recorded universe/window/resources and explicit non-global limitation |
| 7. SERVICE audit | Real eight actions, exact JS extraction failure and eight pending leads |
| 8. ACCOUNTABILITY audit | Captured Itrane rejection, one of four core recovery searches executed |
| 9. Lane-specific protocol | Native lane acquisition plans/configuration; no event/site/run-ID special cases in production logic |
| 10. Mandatory hard research | Independent missing-lane needs even if old combined event minimum met |
| 11. Research/event separation | New completion field; unchanged old event counters; negative adds no events |
| 12. Combined coverage | Per-lane terminal checks and independently deduplicated validated events |
| 13. Production finality | Proof rebuilt; all other research needs remain blocking |
| 14. Editorial absence | OMIT/NO_NEWS/SKIP, no story budget or active-count credit |
| 15. No stale/generic substitution | Temporal/semantic gates retained; original packet preserved |
| 16. Failure precedence | Technical/contract before closure; infrastructure and chronology tests |
| 17. Budget truncation | Core/dynamic obligations audited, cap 8 unchanged, missing three remain blocked |
| 18. Durable provenance | Sealed inputs, primary bytes, state/config, hashes, queries/actions/reasons |
| 19. Offline exact replay | Parent identity checks, repeated derivative replay PASS, guarded zero calls |
| 20. Required tests | All ten cases plus additional integrity/production compatibility tests |
| 21. Accepted layers preserved | Diff confined to finality and necessary downstream compatibility; no scheduler/config/retrieval/archive edits |
| 22. Final report | Exact A–M sections, honest blocked production verdict and clean milestone state |
