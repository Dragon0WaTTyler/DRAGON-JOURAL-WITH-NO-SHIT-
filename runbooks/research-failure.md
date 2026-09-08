# Research failure

## Symptoms
Research packet, perspectives, question tree, or evidence budget is incomplete.
## Failure codes
`RESEARCH_PACKET_INVALID`, `RESEARCH_PLAN_INVALID`, `AI_PROVIDER_EXECUTION_FAILED`.
## Likely causes
Provider failure, weak candidates, missing exact sources, or invalid planning inventory.
## Automatic actions
One bounded provider repair and deterministic plan validation.
## Fallback order
Repair affected candidate; use verified alternate; mark section skipped; incident.
## Data never to overwrite
Raw provider response, accepted sources, continuity, and valid sibling desks.
## Retry limit
Two content/validation attempts.
## Stop condition
Stop when required provenance or balanced perspectives remain unavailable.
## Resume behavior
Retry `research` or `research_planning` only as indicated.
## Manual recovery
Exceptional only: approve changed scope while preserving the failed evidence.
