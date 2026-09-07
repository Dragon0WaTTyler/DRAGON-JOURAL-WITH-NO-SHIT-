# DRAGON V5 recovery runbook

## Additional explicit V5 codes

The policy also handles `AI_PROVIDER_UNCONFIGURED`,
`AI_PROVIDER_INTEGRATION_NOT_PROVEN`, `AI_PROVIDER_EXECUTION_FAILED`,
`AI_PROVIDER_RESPONSE_INVALID`, `RESEARCH_PACKET_INVALID`,
`FACTCHECK_FAILED`, `ARABIC_LANGUAGE_QA_FAILED`,
`PUBLICATION_SOURCE_INVALID`, `PDF_QA_FAILED`, `EPUB_QA_FAILED`,
`FINAL_QA_FAILED`, `STAGE_INPUT_INVALID`, `STAGE_ACCEPTANCE_FAILED`,
`STAGE_RESULT_INVALID`, and `STAGE_STATE_UPDATE_INVALID`. Environment and
dependency codes block; the one execution-transient code retries twice;
content/validation codes target only their stage; interface violations create
an incident as code defects. Never broaden a targeted retry to valid sibling
artifacts.

## Operating rule

Recovery starts after a stage has truthfully failed. It never marks an invalid
artifact complete, never restarts valid upstream checkpoints, never loops
without a configured limit, and never exposes secrets. `--resume` validates
checkpoint hashes. `--retry STAGE` invalidates that stage and its dependents.

For all entries below, inspect `daily-runs/YYYY-MM-DD/state.json`, the named
stage log under `logs/`, and any `recovery/incident-NNN/` packet. Resume with:

```text
python dragon_daily.py --date YYYY-MM-DD --resume
```

Target one stage with:

```text
python dragon_daily.py --date YYYY-MM-DD --retry STAGE
```

## Source and editorial failures

### SOURCE_TIMEOUT

- Meaning/causes: network delay, temporary origin/CDN failure, DNS interruption.
- Inspect: `logs/research.jsonl`, research packet URL and timestamp.
- Safe first action: bounded exponential request retry.
- Automatic repair/max: retry research attempt, maximum 3 total attempts.
- Tests: source timeout and checkpoint-preservation integration tests.
- Resume: `--retry research` only after automatic attempts are exhausted.
- Escalate: incident when repeated sources fail; never invent access or facts.

### SOURCE_INSUFFICIENT

- Meaning/causes: no independent trail, only a homepage, stale or disputed proof.
- Inspect: affected structured research item and source policy.
- Safe first action: search configured alternates for that item.
- Automatic repair/max: targeted item repair, maximum 2 attempts.
- Tests: story-packet/source validation.
- Resume: `--retry research`.
- Escalate: mark section `SKIPPED` with reason or require intervention; no filler.

### ARTICLE_SCHEMA_INVALID / ARTICLE_FACTCHECK_FAILED

- Meaning/causes: missing required fields, unsupported claims, attribution or
  number/date contradiction.
- Inspect: affected article, source mapping, fact-check record and stage logs.
- Safe first action: isolate the smallest article/claim.
- Automatic repair/max: targeted editorial-unit repair, maximum 2 attempts.
- Tests: schema, source mapping and fact-check gates for that unit plus regression.
- Resume: `--retry article_generation` or `--retry factcheck` as appropriate.
- Escalate: remove/skip the item or create incident; uncertainty stays explicit.

## Arabic, cover, and publication failures

### ARABIC_RENDERING_FAILED / RTL_LAYOUT_FAILED

- Meaning/causes: missing font, unsupported renderer, wrong `lang`/`dir`, mixed
  direction overflow or broken shaping.
- Inspect: `preflight.json`, `logs/arabic_language_qa.jsonl`, publication HTML,
  CSS, rendered QA report.
- Safe first action: verify configured local font and RTL metadata.
- Automatic repair/max: repair/rerender the affected source or binary, 2 attempts.
- Tests: Arabic fixture render, extraction, mojibake, RTL HTML/XHTML and layout.
- Resume: `--retry arabic_language_qa`, `--retry publication_source`, or
  `--retry pdf` according to the failing artifact.
- Escalate: incident after two attempts; never substitute transliteration.

### COVER_FAILED

- Meaning/causes: generation unavailable, invalid asset, visual QA failure,
  noncanonical or missing final-edition identity.
- Inspect: cover brief, cover log, exact declared asset.
- Safe first action: one simpler generation attempt or configured SVG fallback.
- Automatic repair/max: cover-only, 2 attempts total.
- Tests: canonical path, dimensions, metadata and page-1 integration.
- Resume: `--retry cover`.
- Escalate: block if neither real generated asset nor accepted fallback passes.

### PDF_BROWSER_CRASH / PDF_CONTENT_MISMATCH / PDF_BLANK_PAGE

- Meaning/causes: renderer crash, stale inputs, font/layout fault or lost prose.
- Inspect: `logs/pdf.jsonl`, render receipt, HTML/CSS, input and output hashes.
- Safe first action: revalidate source identity; retry crash, otherwise repair PDF
  source/layout only.
- Automatic repair/max: PDF-only, 2 attempts.
- Tests: openability, size, page-1 cover, prose/section presence, Arabic
  extraction, blank pages and resource restrictions.
- Resume: `--retry pdf`.
- Escalate: incident; preserve valid editorial and EPUB-independent checkpoints.

### EPUB_XML_INVALID / EPUB_MISSING_RESOURCE

- Meaning/causes: malformed XHTML/OPF/nav, bad manifest/spine/link or absent asset.
- Inspect: `logs/epub.jsonl`, EPUB validation output and archive member list.
- Safe first action: repair the exact XML/resource mapping.
- Automatic repair/max: EPUB-only, 2 attempts.
- Tests: ZIP/mimetype/container/OPF/nav/XHTML/RTL/cover/resource/link suite.
- Resume: `--retry epub`.
- Escalate: incident; never rerun research, editing, cover or PDF.

## Archive and delivery failures

### GIT_PUSH_FAILED / GITHUB_READBACK_MISMATCH

- Meaning/causes: authentication, branch protection, network, concurrent remote
  update or byte mismatch.
- Inspect: `logs/github_archive.jsonl`, local/remote revisions and archive receipt.
- Safe first action: fetch and diagnose; never force-push.
- Automatic repair/max: archive-only exponential retry, 3 attempts.
- Tests: rejected push, concurrent update and exact hash read-back.
- Resume: `--retry github_archive`.
- Escalate: publication remains COMPLETE; archive becomes FAILED with incident.

### WHATSAPP_SEND_FAILED

- Meaning/causes: missing/expired credential, provider/network error, unsupported
  document attachment or recipient configuration.
- Inspect: redacted `logs/whatsapp_delivery.jsonl` and delivery receipt.
- Safe first action: retry the same idempotent delivery request.
- Automatic repair/max: delivery-only exponential retry, 3 attempts.
- Tests: mock failure/retry and duplicate-send prevention.
- Resume: `--retry whatsapp_delivery`.
- Escalate: publication remains COMPLETE; delivery becomes FAILED with incident.

## Code defects and unknown failures

### UNKNOWN_CODE_DEFECT / UNHANDLED_STAGE_EXCEPTION

- Meaning/causes: reproducible implementation defect outside a known stage error.
- Inspect: complete incident packet and targeted source files.
- Safe first action: reproduce with the smallest relevant test.
- Automatic repair/max: none unless a local RepairAgent integration has passed
  its isolation/rollback integration test.
- Tests required: targeted reproduction, regression suite, failed-stage rebuild,
  validators.
- Resume: retry only after an accepted minimal patch.
- Escalate: intervention required. A failed repair patch is rolled back.

Unknown failures follow the same incident-first rule. Do not broaden them into an
automatic refactor.
