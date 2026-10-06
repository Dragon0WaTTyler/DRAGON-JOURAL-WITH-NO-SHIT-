# Bounded hard acquisition: October 6 offline proof

Baseline: `e705c4d81916dff324090c031b3b98cfd7d622eb`.
Sealed run: `provider-research-acceptance-2bcc6d20-c696-4b25-8305-01c5bd804b80`.
Manifest: `c33caf1bd2172429684401b94055f75d14aa5c73e1bcbeeb8242de96d138adfe`.
This is an offline allocation comparison, not another live run or a revised
historical verdict. The original remains `HARD_SEARCH_EXECUTION_NOT_ACCEPTED`.
The fixture preserves search result URLs/titles, parent relationships, child
candidates, captured qualification metadata, action identities, and source hashes.
It contains no invented PDF extraction or provider confidence as evidence.

## Root cause and original graph

The mandatory executor's final `reconcile_discovery_leads` loop created a
required fetch for every uninspected lead, even leads excluded by ranked
selection. Finality added all planned hard actions and concrete dynamic
deferrals, including event-feedback searches. Native and provider candidate
paths competed simultaneously. The continuation helper carried required lead
fetches, but selected listing PDFs had no `required_lead_inspection` flag;
their original job lineage did not put them in the continuation slice.
Discovery, inspection selection, evidence obligation, and fallback were thus
conflated. No number of fair reorderings can exhaust this captured graph.

| Lane | Required before | Executed | Missing |
| --- | ---: | ---: | ---: |
| ACCOUNTABILITY | 15 | 8 | 7 fetches |
| SERVICE | 17 | 7 | 9 fetches + 1 follow-up search |
| GENERAL | 1 | 1 | 0 |

The simultaneous requirement is 33 distinct actions against 16 slots.
`CURRENT_HARD_ACQUISITION_CONTRACT_IS_NOT_BOUNDEDLY_SATISFIABLE` applies to
that old all-candidates exhaustion contract, not to every possible early
positive evidence bundle. A run with fewer leads could succeed; the old model
did not bound its obligations by a candidate path.

ACCOUNTABILITY tree: four core actions → canonical Cour des comptes navigation
→ annual-report PDF; window search → several health/news leads → child pages;
separate provider Competition Council candidate → PRIMARY and INDEPENDENT
inspections. The latter was semantically rejected in the sealed run.

SERVICE tree: four core actions → generic maroc.ma navigation → category
children; separate AMMPS provider candidate → notice page → exact PDF;
independent Aujourd'hui page → event-feedback alternative-coverage search.
The PDF remained uninspected and role/origin qualification remained unresolved.

Every old required action appears below. Search-result candidates are
`CANDIDATE_DISCOVERY` records before a fetch exists. Unpromoted siblings are
`ALTERNATE_CANDIDATE`; channel expansions are `FALLBACK`. Corroboration is
required only for the selected path's still-unsatisfied role; extra routes
are `OPTIONAL_CORROBORATION`. Generated child is a relationship, not an
automatic mandatory status. Primary inspection and exact artifact are distinct.

| Lane | Action | Classification | Parent/path | Executed |
| --- | --- | --- | --- | --- |
| ACCOUNTABILITY | `ACT-3F20C91E487F` | CANDIDATE_INSPECTION | `investigations:investigations_01` | yes |
| ACCOUNTABILITY | `ACT-98DC17B494B1` | REQUIRED_CORROBORATION | `investigations:investigations_01` | yes |
| ACCOUNTABILITY | `ACT-66D6E2AF4F1D` | CORE_PROTOCOL | `BREADTH:accountability_and_service:1` | yes |
| ACCOUNTABILITY | `ACT-94460147B118` | CORE_PROTOCOL | `BREADTH:accountability_and_service:1` | yes |
| ACCOUNTABILITY | `ACT-5E5C24CA8046` | CORE_PROTOCOL | `BREADTH:accountability_and_service:1` | yes |
| ACCOUNTABILITY | `ACT-97E4C5286F77` | CORE_PROTOCOL | `BREADTH:accountability_and_service:1` | yes |
| ACCOUNTABILITY | `ACT-03C02631C24D` | ALTERNATE_CANDIDATE | `BREADTH:accountability_and_service:1` | yes |
| ACCOUNTABILITY | `ACT-6C438E521766` | ALTERNATE_CANDIDATE | `BREADTH:accountability_and_service:1` | no |
| ACCOUNTABILITY | `ACT-0F29905AE800` | EXACT_ARTIFACT | `https://www.courdescomptes.ma/publications/` | no |
| ACCOUNTABILITY | `ACT-C8B5A69F89DB` | ALTERNATE_CANDIDATE | `OBS-990E6FB7458B` | no |
| ACCOUNTABILITY | `ACT-D50E764C555D` | ALTERNATE_CANDIDATE | `OBS-27E9CC2A9F57` | no |
| ACCOUNTABILITY | `ACT-6104DAC35C12` | ALTERNATE_CANDIDATE | `OBS-C43E7C3B9613` | no |
| ACCOUNTABILITY | `ACT-0768C0B7AFD1` | ALTERNATE_CANDIDATE | `OBS-34339F7D901B` | yes |
| ACCOUNTABILITY | `ACT-0CA0D1738F78` | ALTERNATE_CANDIDATE | `OBS-45C17B79FD85` | no |
| ACCOUNTABILITY | `ACT-382A4BDDE4E9` | ALTERNATE_CANDIDATE | `OBS-7F5A59B9DAAB` | no |
| SERVICE | `ACT-DD9312A2E042` | CANDIDATE_INSPECTION | `service:service_01` | yes |
| SERVICE | `ACT-5B342524D5E0` | REQUIRED_CORROBORATION | `service:service_01` | yes |
| SERVICE | `ACT-8C690E6FD36B` | CORE_PROTOCOL | `BREADTH:accountability_and_service:2` | yes |
| SERVICE | `ACT-96CA0A4FBC08` | CORE_PROTOCOL | `BREADTH:accountability_and_service:2` | yes |
| SERVICE | `ACT-551114429713` | CORE_PROTOCOL | `BREADTH:accountability_and_service:2` | yes |
| SERVICE | `ACT-3365C5DD828E` | CORE_PROTOCOL | `BREADTH:accountability_and_service:2` | yes |
| SERVICE | `ACT-0CEDC005ABD8` | ALTERNATE_CANDIDATE | `BREADTH:accountability_and_service:2` | yes |
| SERVICE | `ACT-AE09BB226712` | GENERATED_CHILD | `https://maroc.ma/en/news` | no |
| SERVICE | `ACT-D095B5966DE1` | ALTERNATE_CANDIDATE | `OBS-609041421CA3` | no |
| SERVICE | `ACT-668B5EE522C6` | ALTERNATE_CANDIDATE | `OBS-286F86DE1562` | no |
| SERVICE | `ACT-43CE83021898` | ALTERNATE_CANDIDATE | `OBS-6A7EB780CA06` | no |
| SERVICE | `ACT-F844C77BC1C3` | ALTERNATE_CANDIDATE | `OBS-68E4692F760E` | no |
| SERVICE | `ACT-9D3CB074EFAB` | ALTERNATE_CANDIDATE | `OBS-937CA3EC5F26` | no |
| SERVICE | `ACT-49A84E12F8FA` | ALTERNATE_CANDIDATE | `OBS-0C4683B8EF42` | no |
| SERVICE | `ACT-09AD2935EE66` | ALTERNATE_CANDIDATE | `OBS-998C1C9C980F` | no |
| SERVICE | `ACT-D5E355B5CEF3` | EXACT_ARTIFACT | `https://ammps.gov.ma/note-information/depot-des-demandes-dagrement-des-sites-dessais-cliniques-et-dinvestigations-cliniques` | no |
| SERVICE | `ACT-F772D98D0DF4` | REQUIRED_CORROBORATION | `service:service_01` | no |

## Minimum legitimate selected paths

The unchanged `candidate_evidence_policy` allows one exact PRIMARY for a
narrow direct official action or routine verified fact, but requires PRIMARY
and INDEPENDENT for unclassified/reported, contested, serious and scientific
claims. Nothing in the captured uninspected PDFs proves that exception.
The conservative selected paths therefore reserve independent acquisition.

| Lane | Searches | Fetches | Child fetches (subset) | Total |
| --- | ---: | ---: | ---: | ---: |
| ACCOUNTABILITY | 4 | 3 | 1 | 7 |
| SERVICE | 3 | 4 | 1 | 7 |
| GENERAL opportunity | 0 | 1 | 0 | 1 |
| Combined | 7 | 8 | 2 | 15 |

ACCOUNTABILITY: three native searches + canonical fetch + annual-report PDF
+ independent discovery + exact independent inspection. Native STANDARD
search consumption is four, follow-up consumption two or fewer, fetches one
configured plus the selected follow-ups. SERVICE: three native searches +
canonical fetch + AMMPS notice + its selected PDF + independent exact page;
the provider job and native job retain their separate original counters.
This is a minimum acquisition route capable of qualification, conditional on
the fetched content passing every gate, not proof that these artifacts qualify.
If an independent route is already known, ACCOUNTABILITY needs one fewer
search. A proven direct-official PRIMARY-only topology can also need less;
unknown roles never obtain that exception from discovery metadata.

The sealed SERVICE independent page did not establish its evidence role.
Its actual follow-up search `ACT-F772D98D0DF4` requires its own exact-result
inspection. With that recorded uncertainty preserved, SERVICE needs 4 searches
and 5 fetches (9 actions), making the combined route 17 rather than 15. This
captured active path cannot fit the remaining eight slots; it must block.
The 15-action minimum describes a route with qualifying independent content,
not the actual qualification state of the sealed SERVICE page.

## Staged semantics and boundedness

New production scheduling passes a `hard_acquisition` receipt. Legacy calls
without it preserve the previous API behavior. Per mandatory lane:
`DISCOVERED` → `SELECTED_FOR_QUALIFICATION` → action status
`MANDATORY_FOR_CURRENT_CLOSURE_PATH`; siblings remain
`FALLBACK_IF_CURRENT_PATH_FAILS`. Selection is stable until captured exact
content explicitly fails temporal/semantic inspection. Unresolved role or
qualification does not count as failure or acceptance. The existing PRIMARY-only
exception releases optional corroboration only after actual validated, hash-bound
exact PRIMARY qualification; original provider candidate claims are preserved
when computing the unchanged claim-sensitive policy. A serious claim cannot
become routine by dropping its original scope. Reasons remain in the
path receipt; a failed inspection can promote the next deterministic candidate.
No provider confidence, metadata role or snippet qualifies evidence.

Initial discovery completes the native core before selecting candidates in the
continuation epoch. Exact document targets rank ahead of generic children,
then explicit provider routes, then other discovered routes, using stable IDs
as ties. One pending primary child frontier per path prevents recursive branch
fan-out; displaced requests remain alternatives. One ranked result is inspected
for a selected role search; other results remain recorded, not mandatory.
Selected primary plus independent requests stay together. Newly promoted jobs
dispatch inside the same shared round cap, without resetting job counters.

One GENERAL opportunity is preserved across the protocol. Further optional
work cannot pre-book mandatory acquisition capacity. Native core strategies
cannot be replaced by a fetch or a fallback query. A fractional channel-fallback
strategy index is explicitly distinguished from a native core index.

Before scheduling and each acquisition admission, the receipt records
`minimum_remaining_required_actions` and remaining execution capacity. This
includes pending core and selected requests plus missing role-acquisition
reservations: independent search + exact fetch when no route is known, or an
exact fetch after a query. Newly observed required artifacts can increase this
bound. Per-job allowance exhaustion is recorded too. If it cannot fit,
`MANDATORY_PROTOCOL_EXCEEDS_REMAINING_CAPACITY` blocks; finality records
`BLOCKED_MANDATORY_PROTOCOL_CAPACITY`. No third epoch or extra actions appear.
Unused epoch-0 slots cannot enlarge the eight-action epoch-1 limit. Optional
hard lanes retain their previous discovery/follow-up behavior independently.

## Captured BEFORE / offline AFTER

BEFORE: 8 + 8 actions executed, 6 searches, 10 fetches (3 children), 17 unique
missing hard obligations; annual-report and AMMPS PDFs uninspected.

AFTER: the captured epoch-0 ledger leaves one core action plus the selected
ACCOUNTABILITY PDF, two reserved independent acquisitions, and the SERVICE
exact pair: six remaining actions. When the captured selected AMMPS parent
reveals its PDF, that is seven of eight remaining slots. Total minimum is 15
including the preserved GENERAL opportunity. Alternate health/category pages
and unpromoted candidates remain in the receipt and do not crowd out those
requests. The actual captured unresolved SERVICE independent role adds its
follow-up search and an exact-result fetch: nine required actions against eight
remaining. The replay returns `MANDATORY_PROTOCOL_EXCEEDS_REMAINING_CAPACITY`.
This is the permitted AFTER outcome B: truthful structural refusal, not a
fabricated qualifying PDF bundle. The scheduler regression checks artifact
identity/order and active path admission, not just counts. A two-slot
counterfactual is also rejected before any admission with that blocker.

This compares captured routing inputs with the new admission model. It does
not replay uncaptured PDF bodies, execute a provider, or claim the 15-action
route achieved evidence closure. A selected uninspected exact artifact still
blocks even when another fixture bundle would otherwise validate. Genuine
negative closure retains all existing checks; uninspected plausible alternatives
remain unresolved and cannot become verified absence.

## Policy and budget preservation

No configuration or evidence evaluator changed. PRIMARY, independent-origin,
source-origin, temporal/current-operation, semantic, exact-page, child,
claim/support, ACCOUNTABILITY, SERVICE, science, P0 and fail-closed gates remain.
Evidence/contract file hashes are checked against the baseline in the local
offline receipt. The new code rejects or schedules; only existing evaluators
can accept a bundle. Production automation remains PAUSED.

Global cap: 8 actions × 2 epochs = 16 before and after. STANDARD remains
4 searches, 4 configured/ordinary fetches, 4 child follow-ups and 2 rounds.
Child fetch counts are subsets of total fetches, never additional actions.
Historical inputs, sealed run, old replay receipts and edition artifacts are
untouched. Provider targeting and production schedules are unchanged.

## Validation and next milestone

`tests/test_v5_bounded_hard_acquisition.py` forbids socket/provider execution
and covers captured overflow, selected artifacts, alternatives, explicit failure
promotion, independent work, capacity refusal, lane independence, exact priority,
unchanged configuration, and positive/negative finality distinctions.
It also covers late role-query result inspection, qualified PRIMARY-only policy
release, identical hash-bound artifact reuse, both/one/no mandatory lane cases,
and optional SERVICE child behavior. There are 26 new regression cases.
Run this with the hard-capacity, hard-lane, finality, evidence-policy, executor,
provider-targeting and recovery suites, then the complete pytest suite.

Final local verification on October 6: targeted group **186 passed in 22.98s**;
complete Windows suite **1,031 passed, 2 existing platform skips in 285.23s**.
The host browser readiness receipt was requalified after its implementation
hash changed, using operational diagnostics and **68 passing browser controls**;
those diagnostics used zero provider calls and zero research actions. The sealed
offline replay forbids network/provider execution. All 92 sealed artifact hashes
and the original manifest hash still verify. Configuration validation passes.

Offline allocation acceptance is distinct from production acceptance. The next
milestone is exactly ONE separately authorized fresh bounded live acceptance
run. Do not begin article generation or enable production automation.
