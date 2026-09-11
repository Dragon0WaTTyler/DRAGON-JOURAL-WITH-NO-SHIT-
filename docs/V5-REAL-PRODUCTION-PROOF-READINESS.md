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
complete repair diagnostics. The relevant focused regressions passed 58 tests;
the full safe regression baseline is recorded in `docs/V5-TEST-BASELINE.md`.

## Explicit authorization boundary

The following command consumes a new live editorial-provider trial and must
only be run after the owner grants a separate authorization:

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

The real-production proof path is **prepared but blocked on explicit live
authorization**. The configured provider remains `NOT_RUN`, scheduler remains
paused, and no completion state is implied by this document.
