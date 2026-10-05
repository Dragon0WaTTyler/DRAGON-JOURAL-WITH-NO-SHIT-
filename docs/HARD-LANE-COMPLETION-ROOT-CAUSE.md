# Hard-lane completion: pre-change trace

Baseline: `6b38c707bad77a132dfb398bb263790bd7a05ce4`, implementation
`b15cc217`, accepted regression 903 passed / 2 skipped. The existing untracked
October 4 tree is retained. Structural graph access failed (Transport closed);
this trace uses source and sealed machine evidence.

## ACCOUNTABILITY

`build_research_targeting` -> `build_recovery_plan` ->
`build_deep_research_state` -> `plan_research_actions` correctly materializes
four required native recovery strategies plus Itrane's two exact acquisitions.
Physical-request deduplication does not merge the three missing strategies.

`schedule_research_actions` reserves one initial lane opportunity and the exact
complementary source. Its generic reservation and first-wave fairness then
select a general candidate and four breadth first waves. Epoch 0 reaches eight
actions with only one ACCOUNTABILITY recovery strategy selected. Required
strategies ACT-1EB65BE1C83E, ACT-4D0BEADD0AFD and ACT-5C810EDC1C10 are deferred.
The shared RoundActionBudget correctly prevents recursive follow-ups from
stealing those selected slots. There is no provider/route cap responsible.

`pipeline.research_recovery` admits epoch-1 delta needs only when their serialized
signature changes or the provider-no-result rule deferred their initial job.
The partially executed ACCOUNTABILITY need is unchanged and its attempt is
correctly not exhausted; nevertheless it is omitted from epoch 1. That epoch
contains only SERVICE. Finality correctly detects the three missing requests.

## SERVICE

`HttpResearchAdapter` and search adapters call `fetch_and_extract_source`, which
does not forward the existing HTML `ExtractionFallback` interface. Static
extraction raises SOURCE_DYNAMIC_ROUTE_REQUIRED. Executor attrition records
BROWSER_RENDER_REQUIRED but materializes no bounded browser recovery action.
The optional extraction configuration is disabled and integration_test_status
NOT_RUN. There is no proven enabled unattended browser backend to claim usable.

SERVICE executes four native strategies and four recursive navigation fetches.
Those follow-ups run inside the first strategy before later search results are
ranked. They exhaust STANDARD's four follow-up slots and all spare round slots.
Two of the eight later leads are labelled SELECTED_FOR_FETCH, but no associated
request executes. The remaining six also lack inspected content. The current
ledger does not consistently reconcile discovery parents with later exact-page
evaluation or distinguish selection from dispatch. No origin-only deduplication
can truthfully discard these eight different URLs.

## Bounded correction

For new V5 requests, reserve required hard protocols before optional waves,
round-robin across hard lanes, with an edition-wide general opportunity retained.
Carry the exact remaining hard requests and per-job counters into the existing
second epoch; never replay completed requests or add a third epoch. Protect
selected core counters and rank follow-ups after selected core work. Schedule
one explicit dynamic attempt through the existing injected extractor boundary;
unconfigured/failed extraction stays technical. Give every discovered potential
lead a content-bound resolution or explicit capacity/contract/technical blocker.
Keep all eleven finality checks and evidence gates.

## Historical evidence limit

The sealed October 4 run has only its original sixteen request/response packets.
The missing three searches, dynamic extraction and eight lead-page responses
were never captured. An exact replay cannot manufacture them. Preserve the
original replay verdict, and separately audit the new prospective allocation
with deterministic execution fixtures and explicit uncaptured-response limits.
September 27 remains unavailable and waived; no substitute is requested.
