# Deep Research Executor v1

## Purpose and boundary

`dragon.deep_research_executor` executes bounded, provider-neutral research
actions underneath the Deep Research Engine. It does not generate articles,
invoke Codex editorial generation, activate a scheduler, or decide publication
readiness by itself.

The runtime sequence is:

```text
question -> action -> discovery/fetch/extract -> structured observation
-> deep-research state -> optional follow-up -> bounded replan
-> source intelligence -> recovery gate -> article generation
```

The original research packet and source-intelligence report remain checkpoints.
When an adapter executes, its outputs are written as recovered packet/report
artifacts and are normalized again before `research_recovery` decides whether
article generation is allowed.

## Actions and adapters

Actions contain stable identity, branch/question/job IDs, desk, regime, query
or target, known entities/events, seen URLs/origins, finite budget, timeout,
expected result, recovery linkage, and provenance requirements. Supported
actions are discovery, direct/configured fetch, official/independent/archive
search, reference/document extraction, contradiction checking, both evidence
recoveries, and distinct-event search.

`FixtureResearchAdapter` is deterministic and used only in offline tests.
`HttpResearchAdapter` executes only direct fetch actions with the existing safe
HTTP, Trafilatura, and structured-document extraction path. It intentionally
has no search backend. A production stage without an explicitly injected
non-generative adapter records `ADAPTER_UNCONFIGURED` and leaves recovery
fail-closed; it never invents an execution result.

## Open discovery and observations

Configured sources are preferred seeds, not a whitelist. Open discovery is
read-only. Every result becomes a structured observation with URL/source ID,
origin, title, dates, extraction and content-hash fields when available,
source class, discovery method, entities/events, claim and contradiction
candidates, relevance, and provenance.

Observation classes are `LEAD`, `POTENTIAL_EVIDENCE`, `CONTEXT`,
`CONTRADICTION`, `DUPLICATE`, `IRRELEVANT`, and `DEAD_END`. Retrieval alone
always has `publication_evidence: false`. An unknown source becomes a lead;
official and independent material become only potential evidence until normal
verification and downstream gates apply. The deterministic fixture has a
named `FIXTURE_VERIFIED_EXACT_PAGE` marker solely to exercise packet replay;
the HTTP adapter cannot emit it.

## Bounded execution and observability

The existing `QUICK`, `STANDARD`, `DEEP`, and `INVESTIGATIVE_LEAD` budgets now
also cap search and fetch actions. The executor records planned/executed
actions, observations retained or rejected, duplicate URLs/events, recovery
attempts, remaining gaps, consumed action budget, context compression, branch
history, follow-ups, and stop reason in structured JSON.

`NO_NEWS` remains unavailable until a terminal bounded outcome. Repeated,
irrelevant, or duplicate material cannot expand a branch indefinitely.

## Recovery, science, and investigations

Recovery needs map to executable actions. Results then flow through source
normalization, duplicate analysis, event clustering, packet patching, and a
fresh recovery plan. The executor cannot directly mark a need successful.
`NEED_DISTINCT_EVENT` excludes known event IDs and duplicate URLs; another
article about the same event is rejected.

Candidate-linked needs and breadth-only needs use the same route. Breadth
needs are attached to bounded jobs (or create a bounded recovery job when the
seed has no candidates), and the pipeline flattens recorded attempt IDs before
the final recovery plan. This keeps `NEED_WORLD_BREADTH`,
`NEED_ACCOUNTABILITY_AND_SERVICE`, and `NEED_DISTINCT_EVENT` visible through
the final distinct-event decision instead of leaving them as unconsumed plan
entries.

Science adapters for Feynman, PaperQA, and ARS remain `ADAPTER_READY` and
disabled. Science observations cannot become publication evidence merely by
repetition. The hard Super Investigation boundary remains:

`MOROCCO + MEKNES ONLY`

Foreign material may be researched under ordinary journalism or as directly
evidence-linked support for a Morocco/Meknes lead. The executor never creates
a Super Investigation dossier.

## Representative offline replay

`tests/fixtures/deep-research-executor-insufficient-ready.json` supplies the
executor response for a primary-only candidate. The test builds the initial
packet, executes the recovery action, normalizes the resulting source, removes
duplicates, replans recovery, and proves that article generation would be
allowed only after the independent exact page passes that replay.
