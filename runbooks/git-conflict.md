# Git conflict

## Symptoms
Archive push is rejected because remote history moved or merge would conflict.
## Failure codes
`GIT_PUSH_FAILED`.
## Likely causes
Concurrent archive, branch protection, authentication, or incompatible remote changes.
## Automatic actions
Fetch and diagnose; never force-push or rewrite published history.
## Fallback order
Fetch/rebase safe archive commit; retry normal push; incident.
## Data never to overwrite
Remote branch, local edition bytes, receipts, manifests, and historical editions.
## Retry limit
Three archive-only attempts.
## Stop condition
Stop on conflict requiring editorial choice or any non-fast-forward risk.
## Resume behavior
Retry `github_archive`; local publication remains complete.
## Manual recovery
Exceptional only: resolve the exact conflict on a reviewable branch.
