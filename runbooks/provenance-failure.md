# Provenance failure

## Symptoms
A material claim lacks exact source identity, independent origin, or support assessment.
## Failure codes
`CLAIM_GRAPH_INVALID`, `FACTCHECK_FAILED`, `ARTICLE_FACTCHECK_FAILED`.
## Likely causes
Homepage citation, missing source ID, wire copies counted independently, or contradicted evidence.
## Automatic actions
Rebuild the claim graph and hold/remove only the unsupported claim or article.
## Fallback order
Primary evidence; independent origin; explicit partial/contradicted/unavailable label; skip.
## Data never to overwrite
Source records, raw claims, contradictions, and unavailable-evidence reasons.
## Retry limit
Two targeted attempts.
## Stop condition
Stop publication of the affected unit when material support does not pass.
## Resume behavior
Retry claim graph/fact-check and its downstream editorial stages only.
## Manual recovery
Exceptional only: editorial adjudication must be recorded, never silently waived.
