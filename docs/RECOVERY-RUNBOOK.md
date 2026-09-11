# DRAGON V5 recovery runbook

## Operational matrix for additional V5 codes

The detailed families later in this runbook cover the core production errors.
This matrix makes every other configured code operational too. “Inspect” always
includes the stage JSONL log, `state.json`, and an incident packet if present.

| Error code | Meaning / likely causes | Inspect | Safe first action; automatic repair / max | Tests required | Resume / escalation |
| --- | --- | --- | --- | --- | --- |
| `CHANGE_WATCHLIST_INVALID` | Tracked watch targets or their material strategies violate the strict schema | `config/change-watchlist.yaml` and schema validation detail | Repair configuration only; none / 1 block | schema, duplicate-ID, strategy, and enabled-proof tests | restart `--from preflight`; intervention required |
| `SOURCE_MONITORING_REQUIRED_FAILED` | A target explicitly marked required could not be fetched or fingerprinted | `source-monitoring/report.json`, exact URL, content type, and error code | Restore/prove that target; none / 1 block | material fingerprint, failure, and prior-baseline tests | `--retry source_monitoring`; optional target failures only degrade |
| `AI_PROVIDER_UNCONFIGURED` | No unattended editorial command was selected | `config/local-automation.yaml`, provider check output | Configure a supported local command; none / 1 block | provider health and production-schema integration | Run `dragon_provider_check.py`, then `--resume`; intervene until genuine PASS |
| `AI_PROVIDER_INTEGRATION_NOT_PROVEN` | A configured command lacks accepted unattended proof | provider identity, integration evidence, stderr | Run the real health check without prompts; none / 1 block | healthcheck plus one full schema fixture | Record PASS only from evidence, then `--resume`; otherwise intervene |
| `AI_PROVIDER_EXECUTION_FAILED` | Provider failed to start, timed out, or exited nonzero | command path, exit code, redacted stderr | Correct a transient runtime fault; retry / 2 | healthcheck and failed operation replay | `--retry research` or `article_generation`; incident after 2 |
| `AI_PROVIDER_RESPONSE_INVALID` | Stdout was not one valid UTF-8 JSON value | raw redacted response and provider protocol | Remove diagnostics from stdout or repair serialization; targeted / 2 | malformed UTF-8/JSON response tests | Retry affected editorial stage; incident after 2 |
| `RESEARCH_PACKET_INVALID` | Candidate, provenance, ranking, evidence, or explicit no-news schema is incomplete | `research/research-packet.json`, exact source records | Repair only invalid section/source records; targeted / 2 | candidate/evidence/source/no-news schema tests | `--retry research`; emit a reasoned `NO_NEWS` decision for a weak section or incident after 2 |
| `RESEARCH_INSUFFICIENT` | Research has no selected lead, lacks the inherited minimum active-section mix, or misses required coverage | captured research packet, source inventory, selected leads, and coverage counts | Preserve the packet and block; do not invoke article generation / 1 | all-no-news and one-lead/undercoverage preflight plus chaos regression | restore sufficient evidence, then `--retry research`; never turn a no-news section into filler |
| `PROVIDER_REGISTRY_INVALID` | Provider identities, adapters, endpoints, authority, fallback, or provenance policy violate the strict registry schema | `config/provider-registry.yaml` and its schema | Repair configuration only; none / 1 block | schema, duplicate-ID, prompt-context, and adapter tests | restart `--from preflight`; intervention required |
| `PROVIDER_REGISTRY_UNAVAILABLE` | A provider explicitly configured as required lacks a proven adapter | provider registry report and integration evidence | Restore/prove the required adapter or make it optional only through editorial review; none / 1 block | provider-specific integration and fallback tests | restart `--from preflight`; optional provider failures do not qualify |
| `SOURCE_DYNAMIC_ROUTE_REQUIRED` | Static extraction found only a script shell | exact URL, response content type, bounded HTML sample | Use an approved browser fallback for that source only; none / 1 block until adapter is proven | JS-heavy fixture and browser resource-limit integration | retry the affected discovery item; never enable a browser globally |
| `DOCUMENT_EXTRACTION_EMPTY` | Structured material parsed but yielded no substantive content | exact PDF/Office/table bytes and parser report | Repair or reject only that material; targeted / 2 | empty, malformed, and successful structured fixtures | retry the affected extraction; skip after 2 |
| `DOCUMENT_ARCHIVE_LIMIT_EXCEEDED` | DOCX/XLSX member count or expanded bytes exceed safety limits | archive central directory and source identity | Reject/quarantine the material; none / 1 block | ZIP limit and unsafe-path fixtures | obtain a smaller trusted source; intervention required |
| `DOCUMENT_ARCHIVE_UNSAFE_PATH` | Office ZIP contains an absolute/traversal member | central directory and exact source hash | Reject/quarantine; none / 1 block | traversal and containment fixtures | obtain a clean trusted copy; intervention required |
| `DOCUMENT_ARCHIVE_INVALID` / `DOCUMENT_PDF_INVALID` / `DOCUMENT_DOCX_INVALID` / `DOCUMENT_XLSX_INVALID` / `DOCUMENT_JSON_INVALID` / `DOCUMENT_TEXT_ENCODING_INVALID` | Structured material is corrupt, malformed, or wrongly encoded | source bytes/hash, MIME, parser diagnostics | Retry or replace only that material; targeted / 2 | valid/corrupt fixtures for each route | hold the source after 2; never infer missing content |
| `DOCUMENT_PDF_ENCRYPTED` / `DOCUMENT_TYPE_UNSUPPORTED` | Material requires access or a parser not currently approved | exact MIME, encryption state, authorization | Seek an accessible official alternative; none / 1 block | encrypted/unsupported routing fixtures | intervention is required for access or new dependency approval |
| `SOURCE_INTELLIGENCE_INVALID` | Normalized source registry, duplicate analysis, or event clusters violate their deterministic schema | `research/research-packet.json`, `source-intelligence/report.json`, validator detail | Preserve research and stop; none / 1 block | source normalization, wire-origin, event-ID, and schema tests | Patch only the deterministic stage, then `--retry source_intelligence`; intervention required |
| `RESEARCH_PLAN_INVALID` | Selected candidate, perspective map, neutral question tree, or evidence-aware budget is incomplete | research packet, source-intelligence report, research plan | Preserve upstream evidence and stop; none / 1 block | planning inventory, desk perspective, budget, and stability tests | Patch only deterministic planning, then `--retry research_planning`; intervention required |
| `RESEARCH_BUDGET_CONFIG_INVALID` | Signal weights, thresholds, branch/follow-up limits, or context bounds are malformed | `config/research-budget.yaml` and schema detail | Repair tracked policy only; none / 1 block | schema, threshold ordering, scoring, and context-bound tests | `--retry research_planning`; intervention required |
| `DEEP_RESEARCH_CONFIG_INVALID` | Open-discovery policy, finite budgets, context buckets, science boundary, or investigation scope configuration is malformed | `config/deep-research.yaml`, schema detail, runtime fingerprint | Repair tracked configuration only; none / 1 block | deep-research schema and policy tests | restart `--from preflight`; intervention required |
| `DEEP_RESEARCH_STATE_INVALID` | A lead was treated as evidence, a branch/round/depth budget was exceeded, or required context state is missing | `deep-research/state.json`, research plan, source intelligence, recovery needs | Preserve upstream packets and repair only deterministic state construction; none / 1 block | lead, branching, repetition, contradiction, context, and scope tests | `--retry deep_research`; intervention required |
| `RESEARCH_ACTION_INVALID` / `RESEARCH_ADAPTER_RESULT_INVALID` | An executor action or adapter result violates the bounded, structured contract | `deep-research/execution-report.json`, action IDs, adapter output | Preserve original packet; repair or reject only the adapter result; none / 1 block | executor action, observation, duplicate, and recovery replay tests | `--retry deep_research_execution`; intervention required |
| `CLAIM_GRAPH_INVALID` | Claim IDs, article inventory, source lineage, origin counts, or support assessments are inconsistent | articles, source-intelligence report, claim graph | Preserve articles and stop; none / 1 block | exact evidence mapping, missing provenance, contradiction, and inventory tests | Patch only graph construction, then `--retry claim_evidence_graph`; intervention required |
| `MEDIA_CRITIC_INVALID` | Comparison inventory, origin counts, or observation-only constraints are inconsistent | articles, event clusters, source registry, media-critic report | Preserve all inputs and stop; none / 1 block | wire dependence, framing marker, no-motive-inference, and inventory tests | Patch only deterministic comparison, then `--retry media_critic`; intervention required |
| `SCIENCE_INTEGRITY_FAILED` | Paper status, legal full-text state, methods/limitations reading, preprint label, or abstract-only disclosure is inconsistent | science article, exact sources, source registry, material passports | Correct disclosure or remove/hold the scientific claim; targeted / 2 | full-text, preprint, abstract-only, DOI/passport tests | `--retry article_generation` or `science_integrity`; hold after 2, never pretend full-text access |
| `SCIENCE_REPORT_INVALID` | Science report inventory, unique passport identity, or PASS/FAIL consistency is invalid | science inputs and report | Preserve inputs and stop; none / 1 block | science report schema/inventory regression | Patch deterministic report construction, then `--retry science_integrity`; intervention required |
| `INVESTIGATION_DOSSIER_INVALID` | Existing multi-day dossier is unreadable or its case/story identity changed | exact dossier and recovery copy, article story key | Never overwrite; none / 1 block | corrupt dossier, identity, atomic-write, cross-day tests | restore a verified copy or patch reader, then `--retry investigation_engine`; intervention required |
| `INVESTIGATION_GATE_FAILED` | Serious accountability story lacks primary evidence, two origins, counter-evidence, response handling, or clean supported claims | dossier, claim graph, source registry, readiness checks | Preserve dossier and hold/repair only the investigation; targeted / 2 | readiness, counter-position, unsupported accusation tests | retry article or investigation gate; keep dossier open after 2, no daily publication quota |
| `ADVERSARIAL_REVIEW_FAILED` | Independent review found a contradicted claim, unavailable provenance, incomplete material support, or untested alternative framing | affected article, claim graph, research plan, adversarial report | Repair/remove only the named editorial unit; targeted / 2 | adversarial outcome and affected claim regression | `--retry article_generation` or `adversarial_review`; hold the story after 2 |
| `FACTCHECK_FAILED` | Legacy source-linkage fact-check gate failed | article source IDs and `factcheck/report.json` | Restore valid mapping or remove item; targeted / 2 | source-linkage regression | `--retry factcheck`; incident after 2; do not invent evidence |
| `ARABIC_LANGUAGE_QA_FAILED` | Grammar/UTF-8/mojibake/leakage gate failed | `qa/arabic-language.json`, canonical articles | Repair language only, preserving claims; targeted / 2 | Arabic, mojibake, leakage regression | `--retry arabic_language_qa`; incident after 2 |
| `COVER_BRIEF_INVALID` | Final lead identity, mode/variant, text-free art classification, or deterministic RTL typography contract is invalid | final articles, edition plan, cover direction | Preserve editorial bytes; none / 1 block | all cover modes, variants, lead identity, art/text separation | patch direction only, then `--retry cover_direction`; intervention required |
| `ASSET_PROVENANCE_INVALID` | A visual is missing, remote, changed, falsely documentary, or lacks chart/source metadata | `assets-manifest.json`, exact local bytes, source IDs, usage notes | Remove or correctly classify the affected visual; none / 1 block | path containment, hash identity, documentary and chart provenance | `--retry cover` or the future asset-producing stage; intervention required |
| `LAYOUT_PLAN_INVALID` | Active article inventory, page grammar, columns, or no-editorial-authority flag is inconsistent | articles, cover brief, layout plan | Preserve editorial/cover artifacts; none / 1 block | grammar inventory, RTL, component, and fact-authority tests | patch layout planning only, then `--retry layout_direction`; intervention required |
| `DESIGN_SYSTEM_INVALID` | Required tokens, Arabic RTL rules, components, grammars, or bundle files are absent or invalid | `design/`, composed CSS, validation detail | Restore the smallest affected bundle; none / 1 block | design-system contract, Arabic fixture, publication-source regression | `--retry publication_source`; intervention required |
| `PUBLICATION_SOURCE_INVALID` | HTML lost RTL, cover, article, or source identity | `edition.html`, CSS, articles, exact URLs | Rebuild semantic publication source only; targeted / 2 | HTML identity, RTL, URL and cover tests | `--retry publication_source`; incident after 2 |
| `PDF_QA_FAILED` | One or more strict PDF validators failed | `qa/pdf.json`, PDF, HTML, cover | Route to the named PDF issue and rebuild PDF only; targeted / 2 | full PDF QA plus failing regression | `--retry pdf`; incident after 2 |
| `PDF_VISUAL_QA_FAILED` | Contact-sheet heuristics found sparse, repetitive, clipped, or otherwise unsafe page composition | `qa/pdf-visual.json`, `qa/pdf-contact-sheet.png`, `qa/layout-doctor.json` | Let the bounded Layout Doctor change only safe visual parameters; targeted / 2 | visual-density, contact-sheet, keep/revert, and Arabic rendering tests | `--retry pdf`; block and request human layout review after 2 |
| `EPUB_QA_FAILED` | One or more strict EPUB validators failed | `qa/epub.json`, EPUB member/XML inventory | Repair the exact EPUB packaging fault; targeted / 2 | full EPUB validator plus failing regression | `--retry epub`; incident after 2 |
| `EPUBCHECK_FAILED` | W3C EPUBCheck reported a conformance error or fatal | `qa/epubcheck.json`, `qa/epubcheck-raw.json`, message IDs and locations | Repair only the exact package/XHTML/CSS defect, rebuild EPUB, and rerun; targeted / 2 | W3C EPUBCheck plus the failing message regression | `--retry epub`; block after 2 |
| `EPUBCHECK_UNAVAILABLE` / `EPUBCHECK_VERSION_MISMATCH` | Java, the pinned JAR, or exact 5.3.0 version is unavailable | preflight output, `DRAGON_EPUBCHECK_JAR`, local tool cache | Install/point to the official pinned distribution; none / 1 block | version probe and known-good EPUB integration | restart `--from preflight`; intervention required |
| `EPUBCHECK_EXECUTION_FAILED` / `EPUBCHECK_REPORT_INVALID` | Validator crashed/timed out or returned unreadable JSON | process output and raw report path | Retry execution once; never infer PASS from file existence; retry / 2 or block / 1 | subprocess failure and malformed-report tests | `--retry epub`; incident/intervention at limit |
| `FINAL_QA_FAILED` | Required section, cover, format, or Arabic gate is not PASS | `final-qa.json` and referenced QA reports | Repair only the named failed prerequisite; targeted / 2 | affected validator and finality regression | Retry named stage, then `--retry final_qa`; incident after 2 |
| `STAGE_INPUT_INVALID` | Declared input is missing, changed, or outside repository | input hashes and prerequisite outputs | Restore/revalidate the exact dependency; none / 1 block | checkpoint tamper and path-boundary tests | Retry producing prerequisite; intervene if provenance is unknown |
| `RUNTIME_FINGERPRINT_MISMATCH` | V5 code, provider, recovery policy, dependency list, or scheduler script changed after the run began | `runtime_fingerprint`, `runtime_fingerprint_current`, source revision, and the change diff | Preserve existing artifacts; none / 1 block | targeted runtime-boundary test and full regression suite | Review the change, then `--from preflight`; never mix old and new stage checkpoints |
| `STAGE_ACCEPTANCE_FAILED` | Stage returned artifacts that its validator rejected | stage outputs and acceptance detail | Repair the failed stage only; targeted / 2 | stage acceptance plus validator regression | `--retry <stage>`; incident after 2 |
| `STAGE_RESULT_INVALID` | Stage violated the orchestrator result interface | traceback, stage implementation, returned value | Reproduce and make a minimal code fix; none / 1 incident | targeted interface and full regression suite | Retry only after accepted patch; intervention required |
| `STAGE_STATE_UPDATE_INVALID` | Stage requested an illegal top-level state mutation | returned metadata and state schema | Remove or explicitly model the unsafe update; none / 1 incident | state schema, atomicity and full regression suite | Retry only after accepted patch; intervention required |

Never broaden a targeted retry to valid sibling artifacts.

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

### SOURCE_FETCH_FAILED

- Evidence: exact HTTPS URL, transport error class, attempt count, and source-stage log.
- Safe action: retry the affected source only with bounded backoff; then record the unresolved failure.

### SOURCE_URL_UNSAFE / SOURCE_REDIRECT_UNSAFE / SOURCE_RESPONSE_TOO_LARGE

- Evidence: redacted target host, whether the rejection occurred before fetch or before redirect follow, and the configured byte ceiling.
- Safe action: block immediately. Never retry credentials in URLs, local/private/reserved addresses, DNS answers containing non-public addresses, unsafe redirects, or oversized material.
- Manual recovery: supply a verified public exact-source URL or an approved bounded artifact; never weaken the network or byte boundary.

### SOURCE_BLOCKED

- Evidence: exact HTTPS URL and HTTP 401/403 response status.
- Safe action: do not bypass access controls; record the block and route to an approved primary or independent fallback.

### SOURCE_CONTENT_EMPTY

- Evidence: exact HTTPS URL, HTTP status, content type, and zero-byte response.
- Safe action: retry or replace only the affected source and never admit it as evidence.

### SOURCE_INSUFFICIENT

- Meaning/causes: no independent trail, only a homepage, stale or disputed proof.
- Inspect: affected structured research item and source policy.
- Safe first action: search configured alternates for that item.
- Automatic repair/max: targeted item repair, maximum 2 attempts.
- Tests: story-packet/source validation.
- Resume: `--retry research`.
- Escalate: mark section `SKIPPED` with reason or require intervention; no filler.

### ARTICLE_SCHEMA_INVALID / CHIEF_EDITOR_FAILED / ARTICLE_FACTCHECK_FAILED

- Meaning/causes: missing required fields, unsupported claims, attribution or
  number/date contradiction.
- Inspect: affected article, source mapping, chief-editor ranking/conflict report,
  fact-check record and stage logs.
- Safe first action: isolate the smallest article/claim.
- Automatic repair/max: targeted editorial-unit repair, maximum 2 attempts.
- Tests: schema, source mapping and fact-check gates for that unit plus regression.
- Resume: `--retry article_generation`, `--retry chief_editor`, or
  `--retry factcheck` as appropriate.
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
