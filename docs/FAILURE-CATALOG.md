# DRAGON V5 failure catalog

This catalog assigns stable codes and recovery classes. The executable policy is
`config/recovery-policy.yaml`. All loops are finite; exhausting a retry creates
an incident unless the policy explicitly blocks or degrades an optional stage.

| Code | Category | Meaning | Automatic first action |
| --- | --- | --- | --- |
| `CHANGE_WATCHLIST_INVALID` | VALIDATION | The Git-backed source watchlist violates its strict contract | Block before research and repair only the watchlist |
| `SOURCE_MONITORING_REQUIRED_FAILED` | DEPENDENCY | A target explicitly marked required could not be checked | Block before research; optional targets only degrade the monitoring report |
| `SOURCE_TIMEOUT` | TRANSIENT | A source request exceeded its deadline | Bounded exponential retry |
| `SOURCE_FETCH_FAILED` | TRANSIENT | A source request failed before a valid response arrived | Bounded exponential retry, then preserve the exact source failure |
| `SOURCE_URL_UNSAFE` / `SOURCE_REDIRECT_UNSAFE` | VALIDATION | A source target is not absolute HTTPS, contains credentials, is local/private, or a redirect resolves outside the public network | Block immediately; never follow or repair around the safety boundary |
| `SOURCE_RESPONSE_TOO_LARGE` | VALIDATION | A source response exceeds its configured byte limit | Block the material; never increase the limit automatically |
| `SOURCE_BLOCKED` | DEPENDENCY | A source explicitly denied access with HTTP 401/403 | Record the block and use an approved independent or primary fallback |
| `SOURCE_CONTENT_EMPTY` | CONTENT | A successful response contained no source bytes | Retry/replace only the affected source; never treat it as evidence |
| `SOURCE_INSUFFICIENT` | CONTENT | Evidence is too weak for the planned item | Reopen only affected research item or skip with reason |
| `SOURCE_DYNAMIC_ROUTE_REQUIRED` | DEPENDENCY | A script-driven page has insufficient static text | Route only that exceptional source to an approved bounded browser adapter |
| `DOCUMENT_EXTRACTION_EMPTY` | CONTENT | A PDF, Office file, JSON, or table source produced no usable text | Retry/repair only that material or reject it |
| `DOCUMENT_ARCHIVE_LIMIT_EXCEEDED` | VALIDATION | An Office archive exceeds safe member or expanded-byte limits | Block the material; never relax archive limits automatically |
| `DOCUMENT_ARCHIVE_UNSAFE_PATH` | VALIDATION | An Office container declares an absolute or traversal member | Reject/quarantine the material |
| `DOCUMENT_ARCHIVE_INVALID` / `DOCUMENT_PDF_INVALID` / `DOCUMENT_DOCX_INVALID` / `DOCUMENT_XLSX_INVALID` / `DOCUMENT_JSON_INVALID` / `DOCUMENT_TEXT_ENCODING_INVALID` | CONTENT | Structured input is corrupt, malformed, or not valid UTF-8 where required | Retry/replace only that source, then hold it |
| `DOCUMENT_PDF_ENCRYPTED` / `DOCUMENT_TYPE_UNSUPPORTED` | DEPENDENCY | Material needs authorization or an unimplemented parser | Block that source route without weakening evidence rules |
| `ARTICLE_SCHEMA_INVALID` | CONTENT | Generated article violates its schema | Repair only the article |
| `CHIEF_EDITOR_FAILED` | CONTENT | Duplicate, contradictory, or otherwise unsafe edition plan | Repair/remove only the conflicting editorial units |
| `ARTICLE_FACTCHECK_FAILED` | CONTENT | Material claim failed verification | Repair/remove only the affected editorial unit |
| `ARABIC_RENDERING_FAILED` | VALIDATION | Arabic glyph shaping/render validation failed | Inspect font/runtime, rerender affected artifact |
| `RTL_LAYOUT_FAILED` | VALIDATION | Required RTL metadata or layout gate failed | Repair publication source/layout only |
| `PDF_BROWSER_CRASH` | TRANSIENT | PDF renderer process crashed | Retry PDF stage within limit |
| `PDF_CONTENT_MISMATCH` | VALIDATION | PDF does not contain canonical content | Rebuild PDF only after source identity check |
| `PDF_BLANK_PAGE` | VALIDATION | Catastrophic blank interior page detected | Diagnose layout and rebuild PDF only |
| `EPUB_XML_INVALID` | VALIDATION | EPUB XML/XHTML is malformed | Repair EPUB package only |
| `EPUB_MISSING_RESOURCE` | VALIDATION | Manifest or document references a missing file | Repair EPUB resource mapping only |
| `COVER_FAILED` | CONTENT | Neither generated cover nor accepted fallback passed | Retry/fallback cover only |
| `ASSET_PROVENANCE_INVALID` | VALIDATION | A visual is remote, missing, tampered, misclassified, or lacks required documentary/chart provenance | Block the affected visual; never present generated art as evidence |
| `GIT_PUSH_FAILED` | DELIVERY | Normal archive push failed | Retry archive only; never force |
| `GITHUB_READBACK_MISMATCH` | DELIVERY | Remote bytes differ from receipt | Refetch and retry archive only |
| `WHATSAPP_SEND_FAILED` | DELIVERY | Provider did not confirm delivery | Retry delivery only |
| `PREFLIGHT_FAILED` | ENVIRONMENT | One or more blocking machine checks failed | Block before expensive work |
| `PREREQUISITE_INCOMPLETE` | DEPENDENCY | Required upstream checkpoint is invalid/incomplete | Block and preserve upstream state |
| `UNHANDLED_STAGE_EXCEPTION` | CODE_DEFECT | Stage raised outside its declared failure contract | Create incident; repair requires proved mechanism |
| `UNKNOWN_CODE_DEFECT` | CODE_DEFECT | Known evidence indicates an unclassified code defect | Create incident; repair requires proved mechanism |
| `AI_PROVIDER_UNCONFIGURED` / `AI_PROVIDER_INTEGRATION_NOT_PROVEN` | ENVIRONMENT | No proven unattended editorial runtime is available | Block before editorial work |
| `AI_PROVIDER_EXECUTION_FAILED` | TRANSIENT | Configured local provider failed to start or exited nonzero | One bounded retry, then incident |
| `AI_PROVIDER_RESPONSE_INVALID` | VALIDATION | Provider stdout is not the required single JSON value | Targeted provider-stage repair |
| `RESEARCH_PACKET_INVALID` | CONTENT | Research lacks date, provenance, claims, or exact source URLs | Repair research only |
| `RESEARCH_INSUFFICIENT` | CONTENT | Research has no selected lead, too few selected sections, or misses inherited coverage rules, so it cannot form a valid edition | Block before article generation; preserve research and obtain adequate evidence |
| `PROVIDER_REGISTRY_INVALID` | VALIDATION | Discovery-provider configuration violates its strict schema or has duplicate identities | Block before research and repair only the registry |
| `PROVIDER_REGISTRY_UNAVAILABLE` | DEPENDENCY | A provider explicitly marked required is not proven available | Block before downstream research; optional outages remain non-blocking |
| `SOURCE_INTELLIGENCE_INVALID` | VALIDATION | Deterministic normalized-source or event-cluster output violates its strict schema | Block; preserve research and create an incident |
| `RESEARCH_PLAN_INVALID` | VALIDATION | Perspective, question, budget, or selected-candidate inventory is inconsistent | Block; preserve research and source intelligence |
| `RESEARCH_BUDGET_CONFIG_INVALID` | VALIDATION | Tracked signal weights, thresholds, limits, or context bounds violate the strict policy | Block planning and repair only the budget configuration |
| `CLAIM_GRAPH_INVALID` | VALIDATION | Claim inventory, stable identity, source provenance, or assessment structure is invalid | Block before editorial approval |
| `MEDIA_CRITIC_INVALID` | VALIDATION | Source comparison inventory or observation-only contract is invalid | Block before adversarial review |
| `SCIENCE_INTEGRITY_FAILED` | CONTENT | Scientific material passport or full-text/preprint/abstract disclosure gate failed | Repair or hold only the science item |
| `SCIENCE_REPORT_INVALID` | VALIDATION | Science article/passport inventory or report status is structurally inconsistent | Block before adversarial review |
| `INVESTIGATION_DOSSIER_INVALID` | VALIDATION | Existing persistent dossier is unreadable or has conflicting identity/schema | Block without overwrite |
| `INVESTIGATION_GATE_FAILED` | CONTENT | Active investigation lacks primary evidence, independent origins, counter-evidence, response handling, or clean claims | Hold the investigation; preserve dossier |
| `ADVERSARIAL_REVIEW_FAILED` | CONTENT | Independent review found contradiction, unavailable provenance, partial material support, or untested framing | Repair/remove only the affected claim or article |
| `FACTCHECK_FAILED` | CONTENT | An active article lacks accepted source linkage | Repair/remove the affected editorial unit |
| `ARABIC_LANGUAGE_QA_FAILED` | VALIDATION | Arabic language, leakage, or mojibake gate failed | Repair language only without changing facts |
| `COVER_BRIEF_INVALID` | VALIDATION | Final lead, cover mode/variant, art classification, or RTL typography direction is invalid | Block before generating cover bytes |
| `LAYOUT_PLAN_INVALID` | VALIDATION | Active-article inventory or functional page grammar is inconsistent | Block before HTML/PDF/EPUB source generation |
| `DESIGN_SYSTEM_INVALID` | VALIDATION | A required token, RTL rule, component, page grammar, or stylesheet bundle is missing/invalid | Block publication-source generation and repair only the design bundle |
| `PUBLICATION_SOURCE_INVALID` | VALIDATION | Semantic HTML, RTL, cover, article, or source identity failed | Rebuild publication source only |
| `PDF_QA_FAILED` / `PDF_VISUAL_QA_FAILED` / `EPUB_QA_FAILED` / `FINAL_QA_FAILED` | VALIDATION | A structural, raster-visual, format, or strict final acceptance gate failed | Repair the affected output stage; visual QA uses a contact sheet and the Layout Doctor may only change safe presentation parameters |
| `EPUBCHECK_FAILED` | VALIDATION | W3C EPUBCheck reported fatal or error messages | Repair/rebuild EPUB only and rerun EPUBCheck |
| `EPUBCHECK_UNAVAILABLE` / `EPUBCHECK_VERSION_MISMATCH` | ENVIRONMENT | The pinned W3C distribution or Java runtime is absent/wrong | Block at preflight; install the pinned version |
| `EPUBCHECK_EXECUTION_FAILED` | TRANSIENT | The validator process could not complete | Retry EPUB validation within the finite limit |
| `EPUBCHECK_REPORT_INVALID` | VALIDATION | The validator did not produce parseable structured output | Preserve raw output and block; never infer PASS |
| `STAGE_INPUT_INVALID` | DEPENDENCY | A declared consumed input is missing or outside the repository | Block at the exact dependency boundary |
| `RUNTIME_FINGERPRINT_MISMATCH` | DEPENDENCY | The executable V5 runtime/config no longer matches the run's recorded producer | Preserve completed bytes; restart explicitly from `preflight` |
| `STAGE_ACCEPTANCE_FAILED` | VALIDATION | A runner returned artifacts rejected by its validator | Targeted stage repair |
| `STAGE_RESULT_INVALID` / `STAGE_STATE_UPDATE_INVALID` | CODE_DEFECT | Stage code violated the orchestrator interface | Incident; automatic repair only if proved |

Unknown codes classify as `UNKNOWN` and create an incident. Prefix heuristics are
a fallback only; adding a recurring error requires an explicit policy entry and
runbook row.
