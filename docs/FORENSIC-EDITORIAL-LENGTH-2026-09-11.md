# Forensic editorial-length review — 2026-09-11

## Scope and preservation

This is an offline analysis and repair record for provider-trial attempt
`attempt-6d24f562361843da939d2116cb92680e`.  No editorial provider was invoked
while producing this record.  No scheduler was enabled, no paid service was
introduced, and no historical artifact was edited.

The raw evidence remains at
`acceptance/provider-trials/2026-09-11/attempts/attempt-6d24f562361843da939d2116cb92680e/`.
Its SHA-256 identities are:

| Artifact | SHA-256 |
| --- | --- |
| `research.raw.json` | `bbeea224da544ff04210bc236773c991376702ee78b19be105cdc2c3e425b680` |
| `articles.attempt-1.raw.json` | `c8373eb9ac340c2a1790362c061480214755017dc7f3996f59088306f2fbf8b5` |
| `articles.raw.json` | `3686308939bef8ce3ad1516c3b1adef9ceb19f024dccaf090c1581610c67904c` |
| `failure.json` | `54d566432dda4c76e055521623728af313bd81407698c9aa25bf5493329b7d33` |

The former historical evidence also remains unchanged:

| Artifact | SHA-256 |
| --- | --- |
| historical `failure.json` | `9e9ccc8410e2836c5d2de22dfd240cbc02044dca1e665c9971f788cab5be670d` |
| historical `research.raw.json` | `cdbe28b1a1ca2a797670170630f63d9cd034d5fe042e305d9c4eb5dcdf9df232` |
| historical `articles.attempt-1.raw.json` | `e32fcf3e262beb02d56fe55f41027cb5712522253965c8d4365a5f3efda3c15f` |
| historical `articles.raw.json` | `25cc22f51ff2e49c256f58923b00a3c7e2822f1bac4a22c9d44347913f94006b` |

## What the failed attempt actually did

The research packet recorded 15 active selections, 10 sources, and four
origins.  The article operation produced only 12 active articles: `science`,
`culture`, and `investigations` were silently omitted even though their
research candidates were active.  There was no persisted per-article planned
role or word budget in the trial request.

| Article / intended role under repaired contract | Sources carried by raw article | Initial words | Repaired words | Minimum / repaired target | Initial result | Repaired result |
| --- | --- | ---: | ---: | --- | --- | --- |
| `front_1` / LEAD | s5, s8, s9 | 309 | 433 | 350 / 400 | reject | pass |
| `pol_1` / STANDARD | s1 | 272 | 272 | 350 / 400 | reject | reject |
| `eco_1` / STANDARD | s5, s9 | 283 | 283 | 350 / 400 | reject | reject |
| `soc_1` / STANDARD | s1 | 263 | 263 | 350 / 400 | reject | reject |
| `rights_1` / STANDARD | s2 | 257 | 257 | 350 / 400 | reject | reject |
| `me_1` / STANDARD | s9 | 258 | 258 | 350 / 400 | reject | reject |
| `africa_1` / STANDARD | s3 | 260 | 260 | 350 / 400 | reject | reject |
| `world_1` / STANDARD | s5, s8, s9 | 254 | 254 | 350 / 400 | reject | reject |
| `biz_1` / STANDARD | s4 | 260 | 260 | 350 / 400 | reject | reject |
| `tech_1` / STANDARD | s4 | 250 | 250 | 350 / 400 | reject | reject |
| `op_1` / STANDARD | s5, s8, s9 | 262 | 262 | 350 / 400 | reject | reject |
| `service_1` / STANDARD | s5, s8, s9 | 262 | 262 | 350 / 400 | reject | reject |

Initial aggregate: 3,190 words, 12 of 12 under the 350-word hard minimum.
Repair aggregate: 3,314 words, 11 of 12 under minimum.  The repair enlarged
only `front_1` by 124 words.  It did not change article IDs or the source
linkage of the retained articles.

## First bad transition and causal analysis

The first contract failure was at **research planning → accepted research
packet**, before article generation.  Every selected active candidate in the
trial lacked `primary_evidence_source_ids`; 14 of 15 also lacked independent
evidence bindings.  The old validator accepted any referenced source evidence,
so discovery/verification evidence was treated as sufficient for an active
story.  Under the repaired production contract this packet is rejected at
research validation with `RESEARCH_PACKET_INVALID`; it cannot enter the
article provider.

A distinct downstream failure was **article planning → article request**.  The
provider prompt contained a global edition target and a 350-word quality rule,
but no per-article budget, role, or aggregate feasibility ledger.  The old
article validator stopped at the first short article.  Its repair request thus
named only `front_1` (309 words).  After that one repair passed, the next run
stopped at `pol_1` (272 words).  This explains both the 11 remaining short
articles and the 3,314-word total; it was not evidence that the edition was
near the 4,000-word acceptance floor.

The raw research cannot support a compliant 4,000-word V5 edition under the
repaired rules: its active candidates lack the required primary and
independent evidence bindings.  That conclusion is established locally before
any provider invocation, not by retrying or mutating the failed attempt.

## Repair implemented

The canonical `config/editorial-depth.yaml` already defines a 6,000–9,000
word edition target and a 4,000-word hard floor.  The repair derives generation
budgets only from that configuration, while preserving the independent V5
acceptance gates of 350 words per active article and 4,000 words per edition.

For a research packet with 15 selected active candidates, the derived local
budget is 350 / 400 / 600 (minimum / target / maximum) per candidate.  For a
12-article selection, it is 350 / 500 / 750.  The role mapping is explicit:
front-page work is `LEAD`, investigations are `INVESTIGATION`, and other
sections are `STANDARD`.  The repair does not rely on the incomplete historic
role data.

Before article generation, the provider now receives a machine-readable
per-article contract containing article ID, section, candidate ID, role,
minimum/target/maximum, source bindings, and available evidence-item count.
The production research validator requires primary and independent bindings
for every active candidate, and the feasibility guard requires at least 12
active articles for the 4,000-word floor.  Synthetic fixtures retain their
explicit test-only exception.

Article validation now collects every under-length article and reports actual
words, minimum and target, deficits to both, evidence IDs, skipped selected
research candidates, repair linkage changes, repair shortening, and aggregate
raw/valid/minimum/target totals.  A repair request receives that complete
diagnostic ledger, so a provider must preserve valid IDs, bodies and linkage
while addressing every failed article.  A successful provider response alone
still cannot establish publication completeness.

## Verification and review package

The dedicated regression fixture exactly models 309 → 433 for `front_1`, the
unchanged 11 short articles, and 3,190 → 3,314 aggregate words.  Tests cover:

- all-underlength diagnostics and aggregate deficits;
- contract budget derivation and prompt propagation;
- no silent omission of selected active research;
- identifier/source-link preservation and no shortening during repair;
- insufficient coverage and missing primary/independent evidence blocking
  before article invocation;
- the immutable raw trial packet being rejected by the repaired research
  gate, with no article-provider call;
- disabled live scheduling and no live path in the offline budget tests.

The full offline suite completed with **371 passed, 2 skipped**.  The final
chaos receipt is `acceptance/machine/failure-injection/receipt.json`: `PASS`,
152 tests observed, runtime fingerprint
`4cd87aef4a65be1796182cb4fdfaa0cfab67bd198d54764a63f6bfb332f2a2cb`,
and JUnit SHA-256
`65e3f7cc20fee8fc27e080ba07f60378d56276b02cc854e186d85381fa0377e2`.
It includes `article_length_budget: PASS` and `already_complete_rerun: PASS`,
so the new logic and finality regression were exercised without publishing an
edition.  The final acceptance audit remains fail-closed (`BLOCKED`): no
synthetic/real publication promotion, archive read-back, delivery proof, or
cutover evidence was manufactured.

## Direct answers

1. **Why did 11 active articles remain below 350 words?** The request had no
   per-article target or machine-readable budget.  All 12 initial articles
   were 250–309 words; the old validator reported only the first one.
2. **Why did the repair total stop at 3,314 words?** It added 124 words to
   `front_1` only (3,190 + 124) and left the other 11 bodies unchanged.
3. **Did repair receive all deficits at once?** No.  It first received only
   `front_1`; the following validation then exposed `pol_1`.  The repaired
   path now supplies all IDs, counts, article/aggregate deficits and budgets.
4. **Can the current research packet support a 4,000+ word edition without
   filler?** No.  It fails the repaired pre-provider evidence gate because
   active candidates lack required primary and independent evidence bindings.
5. **Has this specific failure mode been removed locally?** Yes.  Offline
   regression tests prove budget propagation, full diagnostics, global repair,
   preservation constraints, and pre-provider rejection; this is not a claim
   that a new live provider output has been accepted.

Historically, the 350-word rule was hard in validation but only a generic
minimum in the provider request, not a per-article enforced instruction.  No
evidence shows an explicit request for concise coverage, but the absent
article budgets let the provider choose concise outputs.  There were no
measured smaller role budgets: there were no role budgets at all.  The V4
brief range does not exempt a V5 required ACTIVE article from its 350-word
floor.  Twelve articles at exactly 350 would mathematically make 4,200 words,
but leave only 200 words of headroom and are therefore not a reliable edition
architecture.  The repaired 6,000-word generation target is derived from the
existing editorial-depth contract, not an arbitrary padding rule.

The human review package is this forensic record, the immutable raw trial
evidence and verified hashes above,
`tests/fixtures/live_provider_length_under_budget.json`, the committed
regressions, and the final test/chaos receipts.  The single Codex scheduler
record was read only: it is `PAUSED`, has the canonical `python
dragon_watchdog.py` command, and configuration still declares one disabled
V5 entry with V4 fallback enabled.

READY_FOR_NEW_LIVE_AUTHORIZATION
