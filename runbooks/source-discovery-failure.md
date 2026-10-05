# Source discovery failure

## Symptoms
Provider registry is invalid, a required adapter is unavailable, or no candidates are discovered.
## Failure codes
`CHANGE_WATCHLIST_INVALID`, `SOURCE_MONITORING_REQUIRED_FAILED`, `PROVIDER_REGISTRY_INVALID`, `PROVIDER_REGISTRY_UNAVAILABLE`, `SOURCE_INSUFFICIENT`.
## Likely causes
Bad watchlist/registry schema, failed required watch target, unproved required adapter, optional outage, or overly narrow query.
## Automatic actions
Validate the watchlist and registry, record health truthfully, and continue past optional outages using configured fallbacks.
## Fallback order
Primary/original; direct specialist; independent reporting; discovery aggregator.
## Data never to overwrite
Prior discovery packets, exact URLs, provider health evidence, and continuity state.
## Retry limit
Registry failures block once; transient discovery uses at most three attempts.
## Stop condition
Stop when no verifiable evidence trail exists; skip the section instead of fabricating a story.
## Resume behavior
Repair configuration then restart from `preflight`, or retry only `research` for transient discovery.
## Manual recovery
Exceptional only: approve a new provider/terms policy and its integration test.
