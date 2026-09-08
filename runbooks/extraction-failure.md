# Extraction failure

## Symptoms
Readable HTML yields no substantial body or the normal extractor is unavailable.
## Failure codes
`EXTRACTION_ADAPTER_UNAVAILABLE`, `SOURCE_EXTRACTION_FAILED`, `SOURCE_EXTRACTION_LOW_QUALITY`.
## Likely causes
Dependency missing, paywall/navigation-only HTML, malformed page, or JS-heavy content.
## Automatic actions
Run bounded Trafilatura extraction and its quality threshold; retain `EXTRACTED_NOT_VERIFIED` status.
## Fallback order
Trafilatura; exact structured document route; approved browser fallback; alternate source; skip.
## Data never to overwrite
Raw fetch hash, canonical/discovered URL, prior extraction, and editorial evidence.
## Retry limit
Two targeted attempts; no unbounded browser loop.
## Stop condition
Stop when extracted text is insufficient or fallback provenance cannot be proved.
## Resume behavior
Retry the affected source unit, then rebuild downstream evidence only.
## Manual recovery
Exceptional only: authorize a browser adapter or document-specific parser with tests.
