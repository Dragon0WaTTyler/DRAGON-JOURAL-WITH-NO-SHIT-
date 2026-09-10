# Editorial-provider trial forensic report — 2026-09-11

## Scope and preservation

This is an offline diagnosis of the one already-authorized 2026-09-11 trial.
It made **no** editorial-provider invocation, did not alter the trial evidence,
and did not run a new edition.  The following raw records are immutable inputs
to this report; their hashes were recorded before the repair work:

| Record | SHA-256 |
| --- | --- |
| `failure.json` | `9e9ccc8410e2836c5d2de22dfd240cbc02044dca1e665c9971f788cab5be670d` |
| `research.raw.json` | `cdbe28b1a1ca2a797670170630f63d9cd034d5fe042e305d9c4eb5dcdf9df232` |
| `articles.attempt-1.raw.json` | `e32fcf3e262beb02d56fe55f41027cb5712522253965c8d4365a5f3efda3c15f` |
| `articles.raw.json` | `25cc22f51ff2e49c256f58923b00a3c7e2822f1bac4a22c9d44347913f94006b` |

There is intentionally no receipt: the trial terminal state was `FAIL`.  Its
recorded source revision was `6beae20b1d3bd4c6faaf95defeaca4d24e5fa3fb` and
its runtime fingerprint was
`aa7f6dc37f5f10c369580c55c5fe99ea4aedc1735f5e23162697624b19849d61`.

## What happened, exactly

The terminal error was:

```
ARTICLE_SCHEMA_INVALID: edition has 1 active articles and 2196 words; minimum is 4000 words
```

`ARTICLE_SCHEMA_INVALID` is an umbrella error code here.  Replaying the
current deterministic article validator against the preserved values gives:

| Provider value | Result |
| --- | --- |
| `articles.attempt-1.raw.json` | `ARTICLE_SCHEMA_INVALID`: 1 active article, 704 words, minimum 4000 |
| `articles.raw.json` | `ARTICLE_SCHEMA_INVALID`: 1 active article, 2196 words, minimum 4000 |

There was no malformed decision object, missing required article field,
duplicate section, invalid status, broken candidate mapping, or bad source-id
reference in either response.  The exact failing rule was the aggregate
edition floor, not an individual JSON-schema violation.

### Causal trace

| Transition | Evidence and result |
| --- | --- |
| Source monitoring / research | One official Ministry of Endowments source (`s1`), published 2026-08-14, said only that lunar observation would occur on 11 September. |
| Research selection | 22 of 23 fixed sections were honest `NO_NEWS`; only `service` selected `c1`.  The alternate `c2` was rank 2 within the same service slot, not a second section. |
| Article prompt | The complete research packet was supplied, including the 4,000-word floor and repair instruction.  The then-current preflight accepted any nonzero selected section. |
| Initial response | Exactly 23 decisions: `service-c1` ACTIVE, all other sections SKIPPED; body 704 words. |
| Initial validation | All shape and provenance checks passed; aggregate edition-word validation failed. |
| Repair prompt | It contained the complete prior list, the exact validation error, and the unchanged research packet.  No filtering or normalizing transformation occurred at this boundary. |
| Repair response | Again 23 decisions, the same service candidate, source id, claims, editorial elements, and status map; only the service body expanded to 2,196 words. |
| Final validation | Aggregate floor failed again.  Publication, fact-check, Arabic QA, finality, archive/read-back, and delivery were therefore never eligible to pass. |

## Initial and repair behavior

The initial ACTIVE item was `service-c1`, mapped to research candidate `c1`
and source `s1`; it had three claims and all required editorial-element
fields.  Its 704-word body was insufficient for the edition floor.

The repair received `previous_articles` as the complete unmodified initial
array.  A structural diff of the preserved values shows:

```
initial_words: 704
repair_words: 2196
status_changes: []
non_body_changes: []
```

Therefore the repair did not delete or silently downgrade an ACTIVE section.
It attempted to solve an edition-level shortfall by enlarging the sole story,
but stopped 1,804 words short of the 4,000-word hard floor.  It could not make
the packet a newspaper because research contained only one publishable section.

The candidate `c2` cannot legitimately be promoted into a second article:
the contract requires exactly one decision per fixed section and an ACTIVE
decision must match that section's selected candidate.  It was merely a
runner-up for `service` and had no independent evidence.

## Root cause and contributing causes

**Root cause:** the former article preflight equated “at least one selected
candidate” with “research sufficient for an edition.”  This was the first bad
transition: the sparse but valid one-lead research packet crossed into article
generation even though no compliant newspaper could result.

Contributors were:

- The source packet contained one official forward-looking notice, not the
  breadth needed for the inherited daily newspaper plan.
- The article prompt stated the 4,000-word floor but did not give research an
  edition-readiness gate derived from the plan.
- Repair was asked to cure an aggregate failure.  With only one valid section,
  expansion was the only evidence-safe action available and it remained below
  the fixed floor.

The research was *valid as a sparse packet* but was **not sufficient for a
daily edition**.  One official source may support a service notice when the
claim records an independent-evidence-unavailable reason; it does not support
inventing the remaining desks or treating that notice as a complete newspaper.

## Hypotheses A–L

| Hypothesis | Finding |
| --- | --- |
| A — Initial output was structurally malformed | Rejected. It had 23 unique decisions and the ACTIVE object passed object-level checks. |
| B — The initial output failed only the aggregate floor | Confirmed: 704 words versus 4,000. |
| C — Repair received a truncated prior response | Rejected. It received the complete initial array. |
| D — Repair altered mappings or source provenance | Rejected. Candidate, source ids, claims, and editorial elements were unchanged. |
| E — Repair silently converted the active story to SKIPPED | Rejected for this trial; status changes were empty. A new guard prevents this class in future repairs. |
| F — The service runner-up could become a second article | Rejected by the one-decision-per-section / selected-candidate mapping rule. |
| G — One official source automatically violates evidence policy | Rejected. The preserved claims include the allowed unavailable-reason treatment; sufficiency, not automatic provenance invalidity, failed. |
| H — The provider response alone justified completion | Rejected. The local acceptance gate correctly rejected both outputs. |
| I — The 4,000-word floor should be lowered | Rejected. It remains unchanged. |
| J — The provider should invent coverage to meet readiness | Rejected. Honest `NO_NEWS` stays required where evidence is absent. |
| K — Research sufficiency needs a derived V2 definition | Confirmed. The former one-lead condition was inadequate. |
| L — Historical trial data should be repaired or retried | Rejected. Raw evidence remains immutable; a future live retry requires fresh explicit authorization. |

## V2 research sufficiency rule

The new rule is derived from the existing inherited editorial architecture,
not from an arbitrary source count or a new word threshold:

1. A packet needs at least **10 selected sections**, the architecture's
   minimum of four lead articles plus six secondary articles.
2. It must meet the inherited coverage rules: Morocco breadth 3; world breadth
   2; reader-life 2; accountability-and-service 2, in their existing section
   groups.
3. Normal per-section evidence, provenance, active-or-explained planning, and
   final article validation remain mandatory.

For context, the existing minimum format plan is already stricter than the
4,000-word floor: four 1,000-word leads plus six 250-word timelines is 5,500
words.  The repair therefore leaves both the 4,000-word hard floor and all
publication gates unchanged.  Readiness blocks only the impossible upstream
case, before a paid or live article-provider invocation.

## Implemented offline repair

- `dragon/config.py` derives readiness from
  `config/edition-architecture.yaml`; V5 already inherits that structure.
- `dragon/providers.py` sends readiness to research, blocks an undercovered
  packet before article generation, and reports the precise missing coverage.
- The production provider factory carries the derived policy; malformed
  readiness configuration fails closed.
- `scripts/codex_editorial_provider.py` makes readiness explicit in the
  research prompt while preserving honest `NO_NEWS` behavior.
- Repair output now has a strict nullable `repair_skip_reason_code` field.
  A selected ACTIVE item may become SKIPPED only with one of
  `EVIDENCE_RETRACTED`, `CANDIDATE_REMOVED`, or `SOURCE_INVALIDATED` plus its
  existing specific skip reason.
- Failure and recovery documentation now distinguish no-lead, undercoverage,
  and normal provider failures.  The chaos inventory includes undercoverage.

No gate was weakened: the 350-word active-article minimum, 4,000-word edition
floor, fact-check, Arabic QA, canonical-cover, PDF/EPUB, finality,
GitHub-read-back, and scheduler rules are unchanged.

## Deterministic regression coverage

The added/updated coverage verifies at least these failure boundaries:

1. inherited architecture derives 10 active sections and all four coverage rules;
2. a preserved one-lead-style packet blocks before any article invocation;
3. a validated provider research response with one lead still blocks;
4. ten leads concentrated in the wrong desks fail coverage;
5. structurally ready research reaches article generation;
6. complete initial article output is sent unmodified to repair;
7. repair preserves candidate mapping on a normal correction;
8. silent ACTIVE-to-SKIPPED repair is rejected;
9. an explicitly coded evidence invalidation is accepted by that narrow guard;
10. the strict structured-output schema and research prompt carry the new
    readiness / repair requirements;
11. existing all-`NO_NEWS`, malformed-output, duplicate-source, checkpoint,
    finality, and synthetic-pipeline regressions remain part of the test and
    chaos suites.

The existing finality and chaos suites are preserved rather than bypassed;
the undercoverage marker joins their catalog as an additional scenario.

## Post-repair validation and production-path review

The offline repair was validated with:

| Check | Result |
| --- | --- |
| Focused provider, contract, and synthetic-pipeline tests | 43 passed |
| Full repository suite | 342 passed, 2 expected skips |
| Hash-bound failure-injection suite | PASS; 136 observed tests and every listed scenario PASS |
| Failure-injection receipt | `acceptance/machine/failure-injection/receipt.json`; JUnit SHA-256 `27536fdacf4bf730e1bc076adb9c811ca3e426aa76ad57f4829c1cf4f1deb5a5` |
| Immutable 2026-09-11 raw evidence | All four hashes still match the table at the top of this report |

The production-path and scheduler review is intentionally negative, not
papered over.  `config/local-automation.yaml` declares exactly one local
Codex scheduler entry, `DRAGON V5 Daily Newspaper`, with canonical command
`python dragon_watchdog.py`; it is explicitly disabled during build-behind.
The current Windows scheduled-task inventory does not contain that task (the
observed `Dragon Telegram Incremental Forward` task is unrelated).  GitHub
archive is also configured disabled, and no real production edition has the
required remote binary read-back receipt.  These are expected migration-state
gaps, but they mean that neither scheduler activation evidence nor the
external production path is verified and the system is **not COMPLETE**.

The final read-only `python dragon_acceptance.py` audit returned `BLOCKED`.
It marked synthetic publication, manual real publication, consecutive
unattended runs, verified Git archive, proven editorial provider, and review
evidence false (WhatsApp delivery is non-blocking/true).  Its completion
checks also correctly show local scheduler activation, V4-fallback retirement,
and competing-GitHub-production disablement as false.  The failed 2026-09-11
trial has no successful receipt and therefore is not counted as provider-trial
acceptance evidence.

## Offline readiness conclusion

The diagnosed failure is fixed at the first invalid transition: undercovered
research cannot invoke the live article provider.  The 2026-09-11 evidence
still records a truthful failed trial and cannot be reclassified as COMPLETE.
A new provider trial is deliberately out of scope until separately authorized.

READY_FOR_NEW_AUTHORIZATION
