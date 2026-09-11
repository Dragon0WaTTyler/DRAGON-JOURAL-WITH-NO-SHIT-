# Source Intelligence and Research Recovery

The V5 source path is: discovery → normalized sources → role classification →
event clustering → candidate evidence eligibility → bounded recovery planning
→ distinct-event/breadth gate → article provider. Discovery never becomes
publication evidence without an exact source page and separate primary and
independent provenance.

`config/source-coverage.yaml` is the machine-readable desk coverage inventory.
It is intentionally a route map rather than an assertion that any listed page
supports a story. `PARTIAL` and `GAP` mark configured limitations honestly; in
particular Meknes, Africa/Sahel, literature, history, investigations and
service lack a fully configured primary-plus-independent route.

`dragon.research_recovery` emits finite needs. Role gaps become
`FIND_PRIMARY_ORIGINAL_EVIDENCE` or `FIND_INDEPENDENT_CORROBORATION`; breadth
gaps become `NEED_*` needs. Every need records its prior source IDs/origins,
target section/event, constraints, attempt limit and stop condition. A later
executor must produce a new verifiable research packet; this slice deliberately
does not make a provider, network, or scheduler call. Exhaustion returns
`RESEARCH_INSUFFICIENT`.

Presentation and story identity are separate. A front promotion and its desk
story may both remain, but their shared event cluster counts once toward
distinct-event completeness and breadth.

RSSHub is **ADAPTER_READY**: the disabled `rsshub-optional` registry entry is
an RSS discovery route only, never evidence, and DRAGON does not depend on a
public instance. The existing internal `change-watchlist` already hashes and
compares official pages while preserving the rule that a change is only a
lead, so changedetection.io is **USE_INTERNAL_WATCHER** for this slice.

Trafilatura remains the default extractor. `config/extraction-adapters.yaml`
records a disabled Crawl4AI boundary. `fetch_and_extract_html` accepts an
explicit injected fallback only after Trafilatura reports a dynamic/low-quality
page; it remains extraction-only and fails closed unless the fallback returns
bounded structured text. Crawl4AI is **ADAPTER_READY**, not installed.

The recovery checks selectively apply SIFT-style practices: trace to the
original source, seek better independent coverage, preserve uncertainty and
contradiction, and retain a verification trail. They intentionally do not add
interactive approvals, AP style, FOIA workflows, or performative ratings.
