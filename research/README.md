# Research packets

For each real run, save one structured packet per desk under
`research/YYYY-MM-DD/`. Packets must conform to `config/output-schema.json`.
They are working research records, not automatically publishable copy.

## Hosted Cloud retrieval contract

Research is performed by the nine Codex editorial roles with the hosted
environment's documented **Internet Access On + allowlist** facility. Roles
may issue ordinary raw HTTPS `GET` requests to allowed source pages. Native
`web__run.search_query` is not a dependency while that surface returns HTTP
401. No repository API client orchestrates roles and no search/API credential
is permitted. Publishing scripts consume already validated packets and never
retrieve editorial evidence.

Every cited record must identify the exact article, report, paper, dataset,
law, archival item, or document page (not a homepage), and record an
Africa/Casablanca retrieval timestamp, publisher, type, attribution, supported
claim, evidence/uncertainty label, and source-trail independence. An HTTP 200
or a repeated wire trail is not corroboration. A blocked or unproductive
search produces a truthful `HOLD`/`REJECT` packet with the pages attempted; it
must never fall back to fixtures, stale claims presented as current,
homepage-only links, `UNKNOWN` filler, or invented facts.

Smoke-test fixtures do not belong here.
