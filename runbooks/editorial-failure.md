# Editorial failure

## Symptoms
Article schema, adversarial review, or chief-editor gate rejects an editorial unit.
## Failure codes
`ARTICLE_SCHEMA_INVALID`, `ADVERSARIAL_REVIEW_FAILED`, `CHIEF_EDITOR_FAILED`.
## Likely causes
Thin copy, duplication, contradiction, missing counter-position, or unsupported framing.
## Automatic actions
Run one bounded unit-level repair with exact validator feedback; otherwise hold/remove it.
## Fallback order
Repair unit; downgrade claim; skip unit; block edition if required integrity fails.
## Data never to overwrite
Raw/failed provider outputs, evidence graph, accepted siblings, and review reports.
## Retry limit
Two targeted attempts.
## Stop condition
Stop when repair would invent facts or alter source meaning.
## Resume behavior
Retry the earliest affected editorial stage and preserve upstream research.
## Manual recovery
Exceptional only: chief-editor intervention with a recorded decision.
