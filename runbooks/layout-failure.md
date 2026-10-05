# Layout failure

## Symptoms
Invalid grammar, sparse/overfull page, clipping, orphaned element, or repetitive composition.
## Failure codes
`LAYOUT_PLAN_INVALID`, `PDF_VISUAL_QA_FAILED`.
## Likely causes
Bad inventory, unsafe component choice, copy-flow imbalance, or visual parameter regression.
## Automatic actions
Layout Doctor makes one least-intrusive spacing/variant change, rerenders, then keeps or reverts.
## Fallback order
Safe spacing; grammar variant; simpler visual component; revert and block.
## Data never to overwrite
Editorial wording/facts, source links, approved cover, and initial diagnostic render.
## Retry limit
One Doctor repair inside at most two PDF-stage attempts.
## Stop condition
Stop if safe parameters cannot pass every structural and visual gate.
## Resume behavior
Retry `layout_direction` for plan defects or `pdf` for render-only defects.
## Manual recovery
Exceptional only: inspect contact sheet and record the exact accepted parameter change.
