# ADR-005: provider-based discovery and routed extraction

- Status: accepted for V5 migration
- Date: 2026-09-08

## Decision

Use a strict local provider registry as the control plane for source discovery.
Every provider declares its role, authority, adapter, endpoint, authentication,
bounded timeout/retry, rate/cache policy, fallback, terms note, classification,
and provenance behavior. Static configuration is not availability: only an
adapter with a passing integration test is `AVAILABLE`.

Use Trafilatura 2.x as the normal readable-HTML extractor. DRAGON performs its
own bounded HTTPS fetch and redirect/content-type checks, then calls
`bare_extraction` for main text and metadata. Output remains
`EXTRACTED_NOT_VERIFIED` until editorial evidence checks pass. Official
documentation: <https://trafilatura.readthedocs.io/en/latest/usage-python.html>.

Use a small native RSS/Atom adapter for feed discovery. Every feed item is
`DISCOVERY_ONLY`. Keep RSSHub disabled and optional until a specific instance,
origin policy, and integration test are accepted. Route PDF, Office, table, and
other non-HTML material to their dedicated parsers; never force them through
the article extractor.

## Alternatives evaluated

| Component | Decision | Reason / revisit condition |
| --- | --- | --- |
| Trafilatura | Adopt for ordinary HTML | Structured text/metadata, local runtime, bounded wrapper, and deterministic fixture tests. Revisit on extraction-quality evidence. |
| Browser/Crawl4AI | Defer as exceptional fallback | A browser for every page is expensive and brittle. Add only after JS-heavy failure fixtures and sandbox/resource limits exist. |
| RSSHub | Optional, disabled | Useful adapter surface but public instances are not a reliable production dependency. Enable only with tested instance/fallback policy. |
| Generic one-parser pipeline | Reject | It loses document structure and encourages false claims about PDFs, tables, and dynamic pages. |
| Provider homepage as evidence | Reject | A seed discovers a trail; it does not verify a claim or prove access to an exact document. |

## Consequences

The editorial provider receives bounded provider hints and an explicit warning
that discovery is not verification. Provider registry health is persisted next
to source-intelligence output. Optional outages cannot kill the newspaper;
anything marked required blocks before downstream editorial work if it is not
proven available.
