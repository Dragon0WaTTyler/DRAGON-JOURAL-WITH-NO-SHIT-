# V5 research finality

This is downstream of the accepted Phase 2 targeting, contract isolation,
retrieval, allocation, provenance and evidence implementation. The current
staged acquisition extension is described in `BOUNDED-HARD-ACQUISITION.md`;
provider schemas, prompts, evidence gates and action caps remain unchanged.
It applies to new V5 decisions; historical bytes and verdicts
are immutable. The September 27 primary-artifact loss and replay waiver remain
recorded in `HISTORICAL-ARTIFACT-STATUS.md`.

## Required protocol

Each requested hard lane has its own native acquisition ladder, materialized
by `plan_research_actions` from the saved job state and exact configuration.
All its core strategies are required, including those deferred by scheduling.
Provider exact artifacts and dynamic acquisitions are also recorded. New V5
production uses the staged protocol in `BOUNDED-HARD-ACQUISITION.md`: only the
selected candidate path's exact artifact and required roles become mandatory.
Non-selected leads and fallback routes remain recorded alternatives. They do
not grant evidence, and plausible uninspected events still prevent verified
absence. An uninspected selected exact artifact blocks positive closure too.

Broad route and alternate-channel expansions generated after empty searches
are contingent on spare capacity. Their deferrals are preserved explicitly as
`deferred_optional_expansions`; they cannot replace any core obligation. The
absence claim is restricted to the recorded protocol and inspected universe.
It does not assert that every configured route or every web result was read.

A duplicate exact acquisition can reuse a fetched artifact from the same lane
and research date with the identical requested URL, extracted text and content
hash. `reused_exact_acquisitions` identifies the original observation and action.
It is not counted as execution. Queries cannot be replaced by exact fetches or
by another language/channel. No budgets or recovery epochs are added.

## Negative-closure acceptance

All checks must pass:

1. The actual saved request contains the mandatory hard target for this date.
2. Exactly one valid explicit provider disposition is preserved.
3. Structured provider attempts with query and purpose are preserved, labelled
   provider-reported rather than independently observed.
4. The target normalization audit accepts the disposition and agrees with its
   surviving candidate count. Target faults block closure. Isolated candidate
   quarantine does not poison an otherwise valid target.
5. The native bounded acquisition/recovery protocol completed, with matching
   requests and action-linked observations. Strategy variants cannot stand in
   for each other. Actual round caps and execution ledgers must agree.
6. No qualifying or potentially qualifying candidate remains unevaluated.
   Semantic rejection is grounded in captured page content, using the existing
   classifier only for rejection/triage, never evidence promotion.
7. No required unresolved technical failure remains. Empty search responses are
   successful emptiness; a JavaScript extraction failure is a dependency block.
   A later observed success of the identical physical request can resolve an
   earlier failure; earlier successes and unrelated emptiness cannot.
8. No target, request identity, or protocol contract failure remains.
9. Capacity was sufficient for every required obligation. A truncated core
   strategy or required concrete follow-up cannot become verified absence.
10. No qualifying validated evidence bundle exists.
11. A closure timestamp is recorded.

The decision preserves date/window, queries/routes, attempts, action counts,
epochs, budget records, observations/content hashes, quarantine, failures,
uninspected leads, optional deferrals, final reason and limitations. Packet,
input and decision hashes bind the proof. Before editorial, the decision is
deterministically rebuilt from its preserved machine inputs.

## States and precedence

| State | Research terminal and eligible? |
| --- | --- |
| `VALIDATED_EVENT` | Yes, after the existing exact-page, semantic, temporal, role, support and independence gates |
| `VERIFIED_NO_QUALIFYING_EVENT` | Yes, only after all negative-closure checks |
| `BLOCKED_TECHNICAL_FAILURE` | No |
| `BLOCKED_CONTRACT_FAILURE` | No |
| `BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH` | No |
| `BLOCKED_MANDATORY_PROTOCOL_CAPACITY` | No; active minimum exceeds remaining global or job allowance |
| `UNRESOLVED` | No; reason `UNRESOLVED_SEARCH_NOT_EXHAUSTED` |

Unresolved technical failure precedes contract failure. In the staged protocol,
uninspected selected acquisitions block even an otherwise valid event; an
impossible active protocol receives the distinct capacity blocker. Unpromoted
alternatives do not block accepted positive closure. Budget truncation precedes
negative closure; incomplete proof remains unresolved. Failure never turns into
news absence. Historical callers without a staged receipt retain their original
finality derivation.

`combined_research_coverage_complete` requires every mandatory hard lane to be
in one of the two acceptable states. `combined_event_coverage` counts real
validated events, deduplicating a native bundle and its selected placement.
The original `editorial_function_coverage` and historical
`COMBINED_COVERAGE_SATISFIED` verdict retain their meanings. `event_coverage_needs`
preserves the event deficits even when their research obligations are complete.

Hard research obligations are independently materialized when the old combined
event minimum was met entirely by another lane. Existing callers without that
new obligation context retain their legacy planning semantics.

Global `research_finality` and `editorial_handoff_eligible` also require all
other existing recovery needs to be satisfied. A negative SERVICE result does
not satisfy another reader-value requirement or a general evidence deficit.

## Editorial absence

The absence plan uses `OMIT_UNSUPPORTED_STORY` and the existing eligible section
inventory. It receives no article word budget, cannot count toward active-item
floors, and cannot become an active article. The editorial payload uses the
existing `NO_NEWS`/`SKIP` shape with an Arabic reason. Sources, facts and original
research packets are preserved; no old event or generic criticism is selected
as a replacement. The full proof remains local, and editorial receives its
decisions, hashes and explicit absence plan.

Research completeness is not publication completeness. Minimum active stories,
word floors, other coverage, claim evidence, fact-check, Arabic QA, canonical
cover, PDF/EPUB and final QA remain in force. An empty newspaper cannot pass.

## Offline durable review

`python dragon_research_finality.py review --provider <sealed-provider-bundle>
--retrieval <sealed-live-bundle> --evidence-review <sealed-evidence-review>`
verifies all three manifests, their lineage, original raw response/request
bytes and all captured action packets. Dispatch comparison excludes only
`actual_information_gain`, which the executor records after the response.

It evaluates the preserved evidence twice, seals a new derivative with the
existing durable acceptance archive, then replays the sealed derivative.
`python dragon_research_finality.py replay <new-bundle>` repeats that exact
offline decision. Neither command has a provider or network adapter.
Original bundles are verified again and are never edited.
