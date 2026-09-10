# DRAGON V5 editorial-provider forensic diagnosis — 2026-09-10

## Scope and evidence integrity

This is an offline diagnosis of the failed live-provider attempt
`attempt-9c1a785e137145c0afcc85c94a1eedb3`.  It does not replay the provider,
change a production gate, or alter the attempted edition.  The evidence below
remains at its original paths and hashes.

| Immutable evidence | SHA-256 | Finding |
| --- | --- | --- |
| `acceptance/provider-trials/2026-09-10/attempts/attempt-9c1a785e137145c0afcc85c94a1eedb3/failure.json` | `f76904f61d8bdcd9d9cbde5ae88c241d2407d7fb0c951766384fab26be45c9bd` | `ARTICLE_SCHEMA_INVALID`: 0 active articles and 0 words, where 4,000 are required. |
| `.../research.raw.json` | `2cbf066ecf180031539544f2aad6086dab9f52fb046a1851c96736a69c984e04` | One source; all 23 section decisions are `NO_NEWS`; no selected candidate. |
| `.../articles.attempt-1.raw.json` | `e282f88cc99938ede2707d0af18bef7041abf556ac75941cf77e0fb9b2c5a9eb` | 23 `SKIPPED`, 0 `ACTIVE`. |
| `.../articles.raw.json` | `3cb7b86045d68f56aa124ead1d8bd79789cb0855ea2d54ff300c8969a94a18a3` | Repair result: again 23 `SKIPPED`, 0 `ACTIVE`. |

The sole source was the official PMNCH event listing
`https://pmnch.who.int/news-and-events/events/109`, dated and retrieved on
2026-09-10.  It advertised an event; it was not itself enough verified news
or evidence for any of the newspaper's sections.  The failed attempt recorded
runtime fingerprint `c70d96501f5885a432c62e7d7ce2be39355ed43770ee9d5dcb60c2fae699fb67`
and source revision `fdc7ee11207e96a642d10e1c2d2e6b826ac0f4cb`.

## Causal trace

| Transition | Observed data | Assessment |
| --- | --- | --- |
| Source data → research output | The provider returned exactly one attributed official event page. Its 23 section decisions all had `status: NO_NEWS`, no candidates, and `selected_candidate_id: null`. | The evidence was inadequate for a publishable article, but the section-level `NO_NEWS` decisions were valid and specific. |
| Research raw → article prompt | `LocalCommandEditorialProvider.research()` stamps only local retrieval time before returning the packet. `articles()` passes that complete packet as `research`; the command adapter serializes it with `json.dumps`. | No source, candidate, section decision, or evidence reference was dropped or filtered. |
| Article prompt → initial output | The prompt says a research `NO_NEWS` section must remain skipped. The initial output therefore returned 23 skipped decisions. | This was a reasonable response. It could not lawfully turn an evidence-free `NO_NEWS` section into an article. |
| Initial output → repair prompt → repair output | The validator correctly rejected the edition-wide total. The repair saw the same research and the same all-skipped result, then returned 23 skips again. | No recovery could make a supported article without new research evidence. The former repair instruction also over-emphasised preserving already-valid skips. |
| Repair output → validator | The validator calculated 0 active articles and 0 words and rejected the result against the 4,000-word gate. | Correct final gate; it must not be weakened. |

The first bad transition was therefore **after structurally valid research was
accepted and before the article-provider invocation**.  The research validator
correctly permits a `NO_NEWS` decision for an individual section, but it had no
edition-capacity guard for a packet with no selected candidate anywhere.  The
article provider was then asked to do an impossible job under the same prompt
and validator rules that prohibited inventing a story.

## Hypotheses A–J

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| A. The model chose `NO_NEWS` even though sufficient candidates were available. | Rejected. | Research raw has zero candidates and zero selected IDs, not hidden candidates. |
| B. Candidate discovery produced candidates that were lost during normalization or serialization. | Rejected. | The article payload is the complete research object; only `accessed_at` is locally normalised. Both raw and downstream decisions have no candidates. |
| C. Candidate eligibility/provenance rules incorrectly discarded usable candidates. | Not evidenced. | The recorded research result contains no candidate to trace through eligibility. The only source is an event listing, so no discarded usable candidate can be shown. |
| D. The no-news criteria were too strict. | Rejected for this attempt. | The only source did not support a verified section story. The problem was not a wrong skip, but treating an all-skip packet as enough to start article generation. |
| E. Aggregate article thresholds were not communicated in time. | Contributing defect. | The article prompt carries the thresholds, but they cannot be met with zero legal active articles; the preflight happened too late. |
| F. Repair was too narrow to recover a systemic failure. | Confirmed. | A repair cannot add evidence absent from research. The old instruction also said to preserve valid decisions verbatim, reinforcing the all-skip result. |
| G. Repair prompt instructions conflicted with the desired correction. | Confirmed contributor. | The old “preserve valid decisions verbatim” language conflicted with a collection-level zero-active failure. It is now scoped to preserve facts and identity, not every skipped status. |
| H. The research prompt under-emphasised active-article / word-count needs. | Contributing design gap. | It allowed a structurally valid all-`NO_NEWS` result to advance. A new deterministic gate makes the capacity requirement explicit before article generation. |
| I. The live provider pipeline did not actually see the expected research/candidate data. | Rejected for the recorded packet. | Raw research and the serialized article input are the same evidence-bearing section data. No missing candidate exists to have been hidden. |
| J. Tests passed on richer synthetic fixtures and missed this edge case. | Confirmed. | Synthetic research contains selected candidates; the new minimized live-shaped all-`NO_NEWS` fixture and regression cover the missing transition. |

## Implemented offline correction

`LocalCommandEditorialProvider.articles()` now calls
`_ensure_research_sufficient_for_articles()` before invoking the article
provider.  If the research packet has no selected candidate, it raises
`RESEARCH_INSUFFICIENT` with source and section counts.  This is classified as
`CONTENT`, with one blocking attempt: preserve the research evidence and retry
research only after adequate evidence exists.  It neither generates filler nor
changes `NO_NEWS` into `ACTIVE`.

The article-repair context now explicitly recognises a zero-active or
aggregate-word failure as collection-level.  The command prompt further says
that only an `ACTIVE` selected research candidate can justify converting a
skipped decision; `NO_NEWS` may never be activated or supplied with invented
evidence.

The regression fixture is
`tests/fixtures/live_provider_all_no_news.json`.  The corresponding test
proves that the exact 1-source, 23-`NO_NEWS`, 0-candidate shape raises
`RESEARCH_INSUFFICIENT` **before any article-provider invocation**.  The chaos
matrix includes this test under `research_insufficient`.

## Validation and review packet

Focused offline regression completed: `33 passed` for editorial-provider,
Codex-provider, chaos, contract, and runbook tests.  Repository-wide regression
completed: `333 passed, 2 skipped in 148.81s`.  The updated chaos matrix passed
all 32 scenarios and observed 128 tests, including `research_insufficient`
(`acceptance/machine/failure-injection/report.json`, runtime fingerprint
`aa7f6dc37f5f10c369580c55c5fe99ea4aedc1735f5e23162697624b19849d61`).

A fresh offline synthetic run, `2099-03-26` / run
`5e7c987a-4813-4938-bac9-b25bead3267f`, reached `final_qa` successfully with
no failure history.  Its optional archive and WhatsApp stages were independently
`DEGRADED`; this does not misrepresent them as passed.  Its full state and
artifact identities are in `daily-runs/2099-03-26/run-report.json`.  The final
acceptance audit result is recorded after its execution below; none of these
commands invokes an editorial provider.

For human review, inspect:

1. the four immutable evidence files and hashes above;
2. this causal trace and the hypothesis table;
3. the deterministic preflight and its regression fixture/test;
4. the post-change full validation results; and
5. the next separately authorized provider attempt, if desired.

## Readiness decision

**READY_FOR_NEW_AUTHORIZATION, contingent on the final acceptance audit below
remaining truthful.**  The specific wasted article-provider invocation is eliminated:
an all-`NO_NEWS` packet now blocks as `RESEARCH_INSUFFICIENT` rather than
spending an article attempt and failing the final word gate.  This does not
claim that a future live research run will find enough evidence, nor does it
make the failed trial pass.  A new live call still requires separate user
authorization and must meet every existing evidence, editorial, fact-check,
Arabic-QA, finality, archive/read-back, and human-review gate.

## Final acceptance audit

`python dragon_acceptance.py` completed on 2026-09-10 with status `BLOCKED`.
It accepted the new `2099-03-26` synthetic local publication and did not
promote this forensic work to acceptance.  Its unsatisfied checks are
`manual_real_publication`, `consecutive_unattended_runs`,
`verified_git_archive`, `editorial_provider_proven`, and `review_evidence`;
the completion checks for enabling the local scheduler and retiring legacy or
competing production paths remain false.  The audit's provider-trial list is
empty because the preserved attempt failed, which is correct.  No acceptance
state, production gate, scheduler, legacy fallback, or remote requirement was
modified by this correction.
