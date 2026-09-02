# Live-retrieval diagnostic — 2026-09-02

**STATUS: BLOCKED**

- Checkout: hosted Codex Cloud, commit `d454e131076f6b31bdea410b184267e7de7aefdb` at Stage 0.
- Diagnostic window: 2026-09-02 16:01–16:03 Africa/Casablanca (UTC+01:00).
- Scope: research transport only. No edition, dated packet, schedule, role topology, or publishing architecture was changed.
- Secret handling: only whether proxy/askpass variables were configured was inspected; no credential or proxy value was printed.

## Stage 0 — contract and implementation inspection

Repository contracts require live current web research for pre-production, prefer source-specific primary plus independent trails, and keep research roles as Codex roles. The repository contains no HTTP/search client for editorial research: `scripts/run_pipeline.py` validates existing packets and sequential gates; it does not retrieve sources. The expected supported path is therefore the native hosted web-search capability available to the Codex run, not a repository scraper or external API.

## Stage 1 — reproduction and cause separation

### Native hosted search: HTTP 401

Method: callable hosted `web__run` tool with `search_query`; no shell, API key, or repository code. A five-class combined request and five separate one-query requests were attempted. Every call failed before returning a search result with:

```text
Fatal error: http 401 Unauthorized: Some("{\"detail\":\"Unauthorized\"}")
```

Classification: **hosted web-search authentication/configuration failure**. The identical tool-level response occurred before any result for every unrelated query/source class. This is not evidence that HCP, Reuters, Al Jazeera, NIST, or Nature rejected a request; no origin response was obtained. It cannot be repaired in repository code without inventing another transport or introducing forbidden credentials.

### Raw HTTPS through the Cloud proxy: proxy 403

Method: shell `curl --location --max-time 15` using the Cloud-provided `HTTP_PROXY`/`HTTPS_PROXY` configuration. Tests were made independently against HTTPS pages at HCP, Reuters, Al Jazeera, NIST, and Nature at 2026-09-02T16:01:31+01:00. Every request failed at CONNECT with no origin HTTP status or response body:

```text
curl: (56) CONNECT tunnel failed, response 403
http_code=000
size=0
```

Classification: **Cloud network/proxy-policy rejection of raw HTTPS CONNECT**, not source-specific blocking. The same pre-origin CONNECT rejection covered five unrelated domains; useful source content was never requested successfully. Raw curl/urllib is not a supported fallback in this environment and must not be used to bypass the policy.

### Official Codex guidance lookup

Method: official `openai-docs` skill helper, `node /opt/codex/skills/.system/openai-docs/scripts/fetch-codex-manual.mjs`, at 2026-09-02T16:01:36+01:00. It could not fetch the official Codex manual. The helper reported a failed HEAD and `ENETUNREACH` for direct port 443 connections. Thus the documentation lookup did not establish an alternate supported repository-side mechanism. The callable native web-search tool remains the appropriate surfaced capability, but its current session authorization is broken.

## Stage 3 — five-class acceptance matrix

A pass requires useful current content, not DNS, homepage reachability, or a source route. None passed.

| Source class | Target/query | Supported native method | Native result | Raw HTTPS control | Useful current content |
|---|---|---|---|---|---|
| Moroccan official/public | `site:hcp.ma Maroc emploi 2026 HCP`; `https://www.hcp.ma/` | Hosted `web__run.search_query` | HTTP 401 Unauthorized, no results | CONNECT 403, `http_code=000`, 0 bytes | **No** |
| International news | `Reuters latest international news September 2026`; `https://www.reuters.com/world/` | Hosted `web__run.search_query` | HTTP 401 Unauthorized, no results | CONNECT 403, `http_code=000`, 0 bytes | **No** |
| Required Palestine source | `site:aljazeera.com Palestine latest September 2026`; `https://www.aljazeera.com/where/palestine/` | Hosted `web__run.search_query` | HTTP 401 Unauthorized, no results | CONNECT 403, `http_code=000`, 0 bytes | **No** |
| AI/technology | `site:nist.gov artificial intelligence latest 2026`; `https://www.nist.gov/artificial-intelligence` | Hosted `web__run.search_query` | HTTP 401 Unauthorized, no results | CONNECT 403, `http_code=000`, 0 bytes | **No** |
| Scientific/research | `site:nature.com latest research September 2026`; `https://www.nature.com/nature/research-articles` | Hosted `web__run.search_query` | HTTP 401 Unauthorized, no results | CONNECT 403, `http_code=000`, 0 bytes | **No** |

Native single-query retests ran immediately after the timestamped 16:01 diagnostics, during the same hosted run. All returned the exact 401 response above. No source content, snippets, dates, or links were returned.

## Stage 4 decision

**STATUS: BLOCKED.** Live research is not reliably working across the five required classes; it is working across zero of five.

Allowed Plus/Cloud action: repair or authorize the native hosted web-search capability for this Codex Cloud task/account, then start a new hosted run and repeat these same five native searches. If workspace/admin policy controls web access, enable the native research/web-search capability for this repository/run; no API key should be added.

What cannot be fixed under the repository constraints: a tool-gateway 401 or Cloud proxy CONNECT policy cannot truthfully be fixed by edition code, pipeline YAML, curl flags, alternate proxies, scraping around access controls, an external search API, or OpenAI API credentials. Those would either be ineffective, change architecture, or violate the execution contract.

Exact next action: Cloud operator/support should restore native `web__run.search_query` authorization for this hosted thread or a fresh hosted task. Re-run the five rows above. Continue to research-only packets only after all five return useful current content with timestamps and source pages. Until then, do not generate an edition and do not substitute `UNKNOWN` filler.
