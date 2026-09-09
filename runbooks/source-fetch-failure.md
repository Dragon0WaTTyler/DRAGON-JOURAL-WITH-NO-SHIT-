# Source fetch failure

## Symptoms
HTTPS fetch times out, targets or redirects to a local/private address, returns an error, or exceeds the byte bound.
## Failure codes
`SOURCE_TIMEOUT`, `SOURCE_HTTP_FAILED`, `SOURCE_URL_UNSAFE`, `SOURCE_REDIRECT_UNSAFE`, `SOURCE_RESPONSE_TOO_LARGE`.
## Likely causes
Origin outage, rate limiting, embedded URL credentials, private/reserved DNS resolution, unsafe redirect, or unexpectedly large material.
## Automatic actions
Reject unsafe targets before opening a connection or following a redirect. Retry only transient public-HTTPS failures with bounded backoff and preserve response metadata.
## Fallback order
Exact origin URL; official mirror; archive reference; independent source; skip.
## Data never to overwrite
Previously fetched bytes/hashes, retrieval timestamps, and successful sibling sources.
## Retry limit
Three transient attempts; unsafe URLs and oversized responses stop immediately.
## Stop condition
Stop when identity, rights, safety, or exact material cannot be established.
## Resume behavior
Retry the affected research/source unit only.
## Manual recovery
Exceptional only: verify a new exact URL or material-size policy without weakening HTTPS controls.
