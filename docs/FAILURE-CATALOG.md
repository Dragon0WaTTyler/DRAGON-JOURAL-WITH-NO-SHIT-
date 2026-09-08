# DRAGON V5 failure catalog

This catalog assigns stable codes and recovery classes. The executable policy is
`config/recovery-policy.yaml`. All loops are finite; exhausting a retry creates
an incident unless the policy explicitly blocks or degrades an optional stage.

| Code | Category | Meaning | Automatic first action |
| --- | --- | --- | --- |
| `SOURCE_TIMEOUT` | TRANSIENT | A source request exceeded its deadline | Bounded exponential retry |
| `SOURCE_INSUFFICIENT` | CONTENT | Evidence is too weak for the planned item | Reopen only affected research item or skip with reason |
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
| `SOURCE_INTELLIGENCE_INVALID` | VALIDATION | Deterministic normalized-source or event-cluster output violates its strict schema | Block; preserve research and create an incident |
| `RESEARCH_PLAN_INVALID` | VALIDATION | Perspective, question, budget, or selected-candidate inventory is inconsistent | Block; preserve research and source intelligence |
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
| `PUBLICATION_SOURCE_INVALID` | VALIDATION | Semantic HTML, RTL, cover, article, or source identity failed | Rebuild publication source only |
| `PDF_QA_FAILED` / `PDF_VISUAL_QA_FAILED` / `EPUB_QA_FAILED` / `FINAL_QA_FAILED` | VALIDATION | A structural, raster-visual, format, or strict final acceptance gate failed | Repair the affected output stage; visual QA uses a contact sheet and the Layout Doctor may only change safe presentation parameters |
| `STAGE_INPUT_INVALID` | DEPENDENCY | A declared consumed input is missing or outside the repository | Block at the exact dependency boundary |
| `RUNTIME_FINGERPRINT_MISMATCH` | DEPENDENCY | The executable V5 runtime/config no longer matches the run's recorded producer | Preserve completed bytes; restart explicitly from `preflight` |
| `STAGE_ACCEPTANCE_FAILED` | VALIDATION | A runner returned artifacts rejected by its validator | Targeted stage repair |
| `STAGE_RESULT_INVALID` / `STAGE_STATE_UPDATE_INVALID` | CODE_DEFECT | Stage code violated the orchestrator interface | Incident; automatic repair only if proved |

Unknown codes classify as `UNKNOWN` and create an incident. Prefix heuristics are
a fallback only; adding a recurring error requires an explicit policy entry and
runbook row.
