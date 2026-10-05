# Clustering failure

## Symptoms
Duplicate groups or stable event clusters violate schema or merge unrelated stories.
## Failure codes
`SOURCE_INTELLIGENCE_INVALID`.
## Likely causes
Malformed source IDs, threshold regression, unstable identity, or origin-analysis defect.
## Automatic actions
Block deterministically and preserve research; no model-based silent repair.
## Fallback order
Exact URL/hash; normalized hash; lexical similarities; manual evidence review.
## Data never to overwrite
Research packet, normalized records, prior event IDs, and investigation links.
## Retry limit
One deterministic attempt.
## Stop condition
Stop when identity cannot be resolved without changing evidence meaning.
## Resume behavior
Patch/test the deterministic stage, then `--retry source_intelligence`.
## Manual recovery
Exceptional only: adjudicate a disputed merge and encode a reproducible rule.
