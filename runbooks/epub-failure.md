# EPUB failure

## Symptoms
Package/XML/RTL/link/cover checks fail or W3C EPUBCheck reports errors.
## Failure codes
`EPUB_QA_FAILED`, `EPUBCHECK_FAILED`, `EPUBCHECK_UNAVAILABLE`, `EPUBCHECK_VERSION_MISMATCH`, `EPUBCHECK_EXECUTION_FAILED`, `EPUBCHECK_REPORT_INVALID`.
## Likely causes
Malformed OPF/XHTML/CSS, missing resource, wrong direction, missing pinned validator, or process fault.
## Automatic actions
Repair the named package defect, rebuild EPUB, rerun internal checks and EPUBCheck 5.3.0.
## Fallback order
Targeted XHTML/metadata/package repair; one process retry; block.
## Data never to overwrite
Canonical article text, cover, valid PDF, raw EPUBCheck report, and failed EPUB hash.
## Retry limit
Two EPUB attempts; unavailable/wrong validator blocks once.
## Stop condition
Stop on any remaining EPUBCheck fatal/error or uncertain canonical lineage.
## Resume behavior
Use `--retry epub`; downstream final QA reruns, upstream artifacts remain.
## Manual recovery
Exceptional only: install the official pinned distribution or diagnose a validator defect.
