# Investigation failure

## Symptoms
Dossier is corrupt or serious accountability material lacks fairness/readiness evidence.
## Failure codes
`INVESTIGATION_DOSSIER_INVALID`, `INVESTIGATION_GATE_FAILED`.
## Likely causes
Identity conflict, missing primary evidence, weak independence, absent counter-evidence, or no response handling.
## Automatic actions
Never overwrite a corrupt dossier; merge idempotently and hold unready publication.
## Fallback order
Restore verified dossier copy; gather missing evidence/response; keep case open; hold story.
## Data never to overwrite
Prior dossier, contradictory evidence, response log, source IDs, and stable case identity.
## Retry limit
One structural attempt or two content-readiness attempts.
## Stop condition
Stop publication on accusation, fairness, identity, or evidence uncertainty.
## Resume behavior
Retry `investigation_engine` after evidence/dossier repair.
## Manual recovery
Exceptional only: legal/editorial review documented in the dossier.
