# Remote read-back failure

## Symptoms
GitHub remote bytes, revision, manifest, or artifact hashes differ from the archive receipt.
## Failure codes
`GITHUB_READBACK_MISMATCH`.
## Likely causes
Stale fetch, wrong branch/path, concurrent update, truncated transfer, or incorrect receipt.
## Automatic actions
Refetch exact remote revision and compare every declared identity without force.
## Fallback order
Refetch; retry archive commit/push; incident with both identities.
## Data never to overwrite
Local canonical edition, remote history, failed receipt, and comparison evidence.
## Retry limit
Three archive-only attempts.
## Stop condition
Stop when byte identity cannot be proved.
## Resume behavior
Retry `github_archive`; do not republish locally or redeliver automatically.
## Manual recovery
Exceptional only: inspect exact revisions/paths and make a normal corrective commit.
