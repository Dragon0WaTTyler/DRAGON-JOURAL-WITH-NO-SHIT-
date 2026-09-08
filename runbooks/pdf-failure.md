# PDF failure

## Symptoms
PDF is missing/corrupt, cover differs, page is blank/sparse, links fail, or Arabic is unreadable.
## Failure codes
`PDF_QA_FAILED`, `PDF_CONTENT_MISMATCH`, `PDF_BLANK_PAGE`, `PDF_BROWSER_CRASH`.
## Likely causes
Renderer/runtime fault, stale input, font/shaping problem, or unsafe pagination.
## Automatic actions
Validate lineage, rerender PDF only, run structural metrics/contact sheet and bounded Layout Doctor.
## Fallback order
Primary renderer retry; safe layout repair; renderer fallback only if explicitly approved; block.
## Data never to overwrite
HTML/CSS, articles, cover, initial failed PDF/report, and valid EPUB.
## Retry limit
Two PDF-stage attempts.
## Stop condition
Stop on mismatch, unreadable Arabic, unsafe repair, or repeated renderer failure.
## Resume behavior
Use `--retry pdf`; never regenerate research/editorial work.
## Manual recovery
Exceptional only: inspect representative previews and preserve the review result.
