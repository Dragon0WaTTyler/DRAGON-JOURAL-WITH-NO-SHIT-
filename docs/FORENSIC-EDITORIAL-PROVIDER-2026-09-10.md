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

## Root cause

**Primary root cause:** the live research provider's source-discovery and
curation turn returned an editorially insufficient corpus—one source, one
origin, zero candidates, and zero selected leads—and the local adapter
accepted that per-section-valid but edition-impossible result.  It then invoked
the article provider even though the article prompt and validator forbade it
from activating any of the 23 `NO_NEWS` sections.

This is a research-output collapse, not evidence of a serialization loss.  The
local system has no pre-research source collection or freshness/quality filter
that could have removed a larger source set: the research prompt itself tells
the provider to perform live web search, and the first local capture is the
provider's returned `research.raw.json`.  The preserved trace cannot establish
why the external research turn chose only that event listing; no per-search
query/tool trace was captured.  It can establish the earliest observable
defect and the deterministic handling required once it occurs.

## Contributing causes

- Research validation required a nonempty source list and valid decisions per
  section, but did not test whether any selected lead existed for the edition.
- The article stage received no extra evidence and was contractually prohibited
  from turning a `NO_NEWS` decision into an `ACTIVE` article.
- Repair was given the same empty research packet.  Its former instruction to
  preserve valid decisions verbatim made repeating valid skips especially
  likely, although no repair wording could create source-backed facts.
- Synthetic fixtures are intentionally much richer: their standard path has
  two sources and candidates for all 23 sections, so it did not represent the
  live all-`NO_NEWS` topology before this regression was added.

## Causal trace

| Transition | Information before and actually forwarded | Loss / interpretation / ability to publish |
| --- | --- | --- |
| Source discovery → `research.raw.json` | The provider was instructed to use live web search and return a deduplicated source array. It returned one PMNCH event listing and 23 `NO_NEWS` sections with no candidates or selected IDs. | This is the first observable bad output. A per-section skip was contractually allowed and conservative, but one event listing could not support a newspaper. |
| `research.raw.json` → verified research object | `_invoke()` captured the raw JSON; `research()` then replaced only `accessed_at` with a local timestamp and validated it. | No source, candidate, section, or evidence ID was lost, filtered, malformed, or collapsed. The then-existing aggregate validation accepted the all-skip packet. |
| Verified research → article input/prompt | `articles()` supplied the complete verified object in `payload["research"]`; `_prompt()` serializes it with `json.dumps`. | The article provider received the same one source and 23 zero-candidate decisions. It had no evidence from which it could lawfully publish. |
| Article input → initial decisions | The prompt says `NO_NEWS` must remain `SKIPPED`; the validator rejects an `ACTIVE` article for a `NO_NEWS` research section. Initial output was 23 skips. | SKIP was valid for every slot and the behavior was intended by the anti-filler contract. The global result was nevertheless incapable of satisfying the edition gate. |
| Initial decisions → repair input/prompt | Repair received the same research packet, the same 23 decisions, and the aggregate error. | No new evidence was introduced. The old repair instruction reinforced preservation of valid skips, so repair returned 23 skips again. |
| Repair decisions → acceptance validator | The validator counted zero active articles and zero body words. | It correctly rejected the edition at the unchanged 4,000-word threshold. No provider response could meet that gate from the supplied evidence. |

The first bad transition was therefore **after structurally valid research was
accepted and before the article-provider invocation**.  The research validator
correctly permits a `NO_NEWS` decision for an individual section, but it had no
edition-capacity guard for a packet with no selected candidate anywhere.  The
article provider was then asked to do an impossible job under the same prompt
and validator rules that prohibited inventing a story.

## Expected versus actual

| Stage | Expected contract behavior | Actual failed behavior |
| --- | --- | --- |
| Research | Return evidence sufficient for at least one selected lead, or surface an edition-level insufficiency before article generation. | Returned a schema-valid all-`NO_NEWS` packet with one source; the adapter treated it as enough to continue. |
| Article generation | Receive one or more selected, evidence-backed candidates and produce source-traceable Arabic articles; skip only unsupported desks. | Received no selected candidates. It correctly skipped every desk but could not create a valid edition. |
| Repair | Correct a malformed or under-length article response using existing evidence. | Repeated the only defensible result because research had no usable lead. |
| Final validation | Reject less than 4,000 valid words or zero active articles. | Correctly rejected 0 active articles / 0 words. |

## Hypotheses A–J

| Hypothesis | Result | Evidence |
| --- | --- | --- |
| A. Research collapse: only one usable source reached research where the architecture expected many. | Confirmed. | The failed packet has 1 source / 1 origin / 0 selected leads. Earlier 2026-09-10 captured research packets have 3 sources / 3 leads, 4 / 4, and 7 / 12 respectively. |
| B. Serialization/input bug: multiple sources existed but only one survived. | Rejected. | The first local capture already contains one source. The only subsequent normalization is `accessed_at`; article payload serialization includes the entire research object. |
| C. Schema mismatch: candidates were misread because fields/types changed. | Rejected. | There were no candidates to misread; both the research schema and article validator require the same selected-candidate identity. |
| D. Over-strict SKIP criteria made skipping easier than supported writing. | Rejected for this packet. | The single event listing did not supply a supported lead. Its 23 skips were intended anti-filler behavior, not an over-strict rejection of present evidence. |
| E. Candidate/evidence disconnect left slots without source-backed evidence. | Confirmed. | All 23 research sections had empty `candidates` and `selected_candidate_id: null`. |
| F. A global failure was expressed as 23 local skips instead of `RESEARCH_INSUFFICIENT`. | Confirmed. | The all-skip packet was structurally accepted and spent an article call before the aggregate validator found the inevitable zero. |
| G. Repair prompt weakness repeated insufficient evidence. | Confirmed contributor. | Repair received no new research and the former wording preserved valid decisions verbatim. |
| H. Prompt regression made the model newly conservative. | Not supported. | The code diff from `a9dba4f` to failed revision `fdc7ee1` changes only documentation; immediately prior live attempts under the same prompt returned 3–7 sources and 3–12 leads. |
| I. Filtering regression discarded legitimate sources before invocation. | Rejected for local code. | No local discovery/filter stage precedes provider research. The provider's returned raw packet is captured before local validation; the preserved evidence cannot prove an external search omission. |
| J. Fixture/live divergence hid the edge case. | Confirmed. | Standard test research contains two sources and selected candidates for all 23 sections; the new fixture mirrors 1 source / 23 `NO_NEWS` / 0 selected. |

## Implemented offline correction

`LocalCommandEditorialProvider.articles()` now calls
`_ensure_research_sufficient_for_articles()` before invoking the article
provider.  If the research packet has no selected candidate, it raises
`RESEARCH_INSUFFICIENT` with source and section counts.  This is classified as
`CONTENT`, with one blocking attempt: preserve the research evidence and retry
research only after adequate evidence exists.  It neither generates filler nor
changes `NO_NEWS` into `ACTIVE`.

The selected-lead check is deliberately the narrow deterministic criterion
that the current contract can prove.  A selected candidate is mandatory for
every `ACTIVE` article and a `NO_NEWS` section can never become active; with
zero selected leads, no possible article response can pass.  No arbitrary
minimum source count, origin count, desk count, or word budget was added:
there is no accepted live trial from which to derive such a threshold, and
the preserved attempts show that 3–7 sources can produce materially different
candidate coverage.  Those quality metrics remain useful future research
planning signals, but would need a separately contracted and evidenced
threshold rather than a forensic-test convenience rule.

The article-repair context now explicitly recognises a zero-active or
aggregate-word failure as collection-level.  The command prompt further says
that only an `ACTIVE` selected research candidate can justify converting a
skipped decision; `NO_NEWS` may never be activated or supplied with invented
evidence.

The regression fixture is
`tests/fixtures/live_provider_all_no_news.json`.  The corresponding test
proves that the exact 1-source, 23-`NO_NEWS`, 0-candidate shape raises
`RESEARCH_INSUFFICIENT` **before any article-provider invocation**.  The chaos
matrix includes this test under `research_insufficient`.  A second regression
passes a fully schema-validated all-`NO_NEWS` packet through `research()` and
proves that only the research operation ran; `articles()` was never invoked.

## Validation and review packet

Focused offline regression completed: `34 passed` for editorial-provider,
Codex-provider, chaos, contract, and runbook tests.  Repository-wide regression
completed: `334 passed, 2 skipped in 148.89s`.  The updated chaos matrix passed
all 32 scenarios and observed 129 tests, including `research_insufficient`
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
