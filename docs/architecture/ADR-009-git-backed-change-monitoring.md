# ADR-009: use stage-local Git-backed change monitoring

- Status: accepted
- Date: 2026-09-08
- Replaces: no V5 change-monitoring implementation

## Decision

DRAGON uses `config/change-watchlist.yaml` as its authoritative tracked
watchlist and runs `source_monitoring` after preflight and before editorial
research. It does not install `dgtlmoon/changedetection.io` or start a second
daemon, scheduler, dashboard, or state store. The older
`memory/watchlist.json` is not the V5 monitoring contract.

Each enabled target must have a passing adapter integration test. Requests are
HTTPS-only, time- and size-bounded, and material-aware:

- HTML is reduced to normalized visible text so script/style churn does not
  create false editorial leads.
- JSON is parsed and canonically serialized so object-key ordering is ignored.
- PDFs and other declared binary materials use exact byte hashes.

The stage compares against the newest earlier dated monitor receipt, never a
same-day or future fixture. A first observation creates a baseline. A changed
hash creates a `DISCOVERY_ONLY` candidate for research; it is not verification
and may not support a published claim by itself.

Optional fetch failures produce a truthful `DEGRADED` monitor report without
killing the newspaper. A target explicitly marked `required` blocks research
with `SOURCE_MONITORING_REQUIRED_FAILED`. The report, configuration, schema,
and previous receipt are hash-bound stage inputs/outputs, so retries cannot
silently substitute a different baseline.

No target is enabled in the repository until its real endpoint integration has
been exercised and reviewed. This keeps the capability implemented without
claiming that current external pages are proven available.
