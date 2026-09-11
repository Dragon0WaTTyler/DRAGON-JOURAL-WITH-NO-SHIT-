# V5 real-production proof readiness

## Current safe evidence

The non-generative provider probe passed on 2026-09-11:

```text
python dragon_provider_check.py
```

It verified the configured executable boundary, Codex CLI version `0.153.4`,
ChatGPT login, unattended capability declaration, and JSON protocol health
operation. It did **not** request research or article generation and did not
change provider promotion state.

Static validation covers the research/articles response schemas, repair schema,
failure classification, immutable raw-capture path, receipts, word budgets, and
complete repair diagnostics. The evidence-eligibility regression set now covers
paired evidence, one-role holds, deterministic linking, same-origin rejection,
ranking demotion, and the preserved 2026-09-11 omission. The full safe
regression baseline is recorded in `docs/V5-TEST-BASELINE.md`.

## 2026-09-11 bounded-trial outcome and offline repair

The one authorized trial is preserved at
`acceptance/provider-trials/2026-09-11/attempts/attempt-e5d8cb6026524a25ab8afdefcc300d7c/`.
It failed before article generation with `RESEARCH_PACKET_INVALID`: selected
`front_1` named independent source `s02` but omitted a primary evidence ID.
The failure receipt's raw SHA-256 matches `research.raw.json`:
`aa74a53c825eb302583fd55f902c00d2330a9b0b9fc490f5969b34888261805e`.

The offline repair preserves the primary-plus-independent gate. It now derives
an omitted role link only when a candidate already references an unambiguous
typed verification source, rejects overlapping source origins, and evaluates
evidence eligibility before keeping a selected candidate. On replay,
`front_1` is correctly linked to real official source `s01` and independent
source `s02`. Candidates without a distinct pair are recorded as
`RESEARCH_INCOMPLETE` and their sections become `NO_NEWS`; they cannot reach
article generation. The replay retained five eligible sections, below the
configured ten-section minimum, so the existing pre-article gate returned
`RESEARCH_INSUFFICIENT` without an article-provider call. This is a repaired
offline sub-blocker, not a successful live edition.

## Future authorization boundary

The 2026-09-11 authorization has been consumed. The following command would
consume a new live editorial-provider trial and must only be run after the
owner grants a fresh separate authorization:

```text
python dragon_provider_check.py --full --date YYYY-MM-DD
```

It writes a new immutable attempt directory under
`acceptance/provider-trials/YYYY-MM-DD/attempts/`, captures raw structured
research and article responses, validates them, and records either a redacted
failure or a `VALIDATED_AWAITING_HUMAN_REVIEW` receipt. It does not promote the
provider, activate the scheduler, publish an edition, archive artifacts, or
claim human review.

The pre-live readiness check is currently PASS with the scheduler paused:

```text
python dragon_live_readiness.py --automation-file \
  C:\Users\walid\.codex\automations\dragon-v5-daily-newspaper\automation.toml
```

## Human review package after a successful real V5 edition

The reviewer must receive hash-bound copies or paths for:

- provider receipt and raw-capture hashes;
- canonical `edition.md`, `articles.json`, `sources.json`, and claim graph;
- article budget contract and repair diagnostics, when any repair occurred;
- fact-check, Arabic QA, cover brief/asset, layout plan, publishing report;
- PDF, contact sheet/visual report, EPUB, EPUBCheck report, and final QA;
- final manifest, run state/report, archive receipt, and remote read-back
  result when archive is enabled.

Only a human review with the receipt hash and the required review checks can
move a technically valid provider trial forward. A production edition remains
ineligible until final QA passes; archive and delivery remain separate
downstream outcomes.

## Phase-2 status

The real-production proof path is **blocked**. Its offline research-packet
sub-blocker is repaired, but the bounded trial failed, the configured provider
remains unproven, scheduler remains paused, and no completion state is implied
by this document.
