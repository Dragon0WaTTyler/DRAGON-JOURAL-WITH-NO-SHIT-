# Cover failure

## Symptoms
Lead identity, mode, art classification, Arabic typography, or canonical cover bytes fail.
## Failure codes
`COVER_BRIEF_INVALID`, `COVER_FAILED`.
## Likely causes
Stale lead, unsupported variant, text inside generated art, shaping fault, or persistence error.
## Automatic actions
Validate brief, generate text-free art, apply deterministic Arabic typography, then one fallback.
## Fallback order
Approved editorial art; source image; deterministic graphic; accepted SVG/equivalent fallback.
## Data never to overwrite
Final lead/article facts, accepted prior cover, and art provenance classification.
## Retry limit
Two cover-only attempts.
## Stop condition
Stop if no truthful, legible canonical cover passes.
## Resume behavior
Retry `cover_direction` or `cover`; do not rerun editorial stages.
## Manual recovery
Exceptional only: human art-direction approval recorded with exact asset identity.
