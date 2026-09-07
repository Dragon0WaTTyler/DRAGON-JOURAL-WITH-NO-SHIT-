# DRAGON V5 failure catalog

This catalog assigns stable codes and recovery classes. The executable policy is
`config/recovery-policy.yaml`. All loops are finite; exhausting a retry creates
an incident unless the policy explicitly blocks or degrades an optional stage.

| Code | Category | Meaning | Automatic first action |
| --- | --- | --- | --- |
| `SOURCE_TIMEOUT` | TRANSIENT | A source request exceeded its deadline | Bounded exponential retry |
| `SOURCE_INSUFFICIENT` | CONTENT | Evidence is too weak for the planned item | Reopen only affected research item or skip with reason |
| `ARTICLE_SCHEMA_INVALID` | CONTENT | Generated article violates its schema | Repair only the article |
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

Unknown codes classify as `UNKNOWN` and create an incident. Prefix heuristics are
a fallback only; adding a recurring error requires an explicit policy entry and
runbook row.
