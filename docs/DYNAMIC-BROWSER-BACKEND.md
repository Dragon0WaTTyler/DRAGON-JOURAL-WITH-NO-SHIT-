# Optional dynamic browser backend

The ordinary retrieval adapter remains trafilatura. Only the existing explicit
dynamic recovery route invokes `crawl4ai-optional`. Extraction still returns
`EXTRACTED_NOT_VERIFIED`; all semantic, temporal, provenance, primary and
independent evidence checks remain downstream.

## Runtime and registration

Production Python 3.14 calls a pinned isolated CPython 3.13 worker using an
argument list, `shell=False`, isolated imports and a minimal environment without
provider credentials. JSON requests allow only acquire or operational probes,
one URL, a private workspace, bounded timeout and action lineage. JSON responses
include exit/stderr information, hashes, timestamps and classified failures.

The Windows host assigns the native worker to a Job while suspended, then
resumes it and releases the request. The worker verifies membership before
importing Crawl4AI. Microsoft Store activation wrappers and the probed Edge
WinRT helper failed this containment requirement. The qualified path uses the
existing Playwright Chromium executable, Crawl4AI 0.9.4 and Playwright 1.63.0.
No dependencies are installed into production Python. The official
[CPython 3.13.14 release](https://www.python.org/downloads/release/python-31314/)
publishes the embeddable runtime's checksum; the local runtime inventory also
hashes its DLL, stdlib ZIP, `_pth`, browser and relevant dependency code.

`dynamic_extractor_from_config` requires the existing YAML enabled/PASS gate
and a local `runtime.json` binding in the common Git directory's
`dragon/dynamic-browser` directory. A YAML PASS alone cannot enable the route.
`DynamicBrowserExtractor.readiness` requires a receipt with all mandatory
checks, unchanged code/runtime/dependencies, unchanged captured proofs, limits
and a timestamp no older than 24 hours. Missing, changed or stale proofs return
`SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE` with reasons. Readiness is host-specific.

`dragon_browser_readiness.py offline-probe` runs the actual adapter against a
fixed worker-owned JavaScript fixture. `probe` runs the actual adapter against
a public HTTPS target. Both are operational diagnostics, never research
evidence. `qualify` requires distinct captures plus the passed focused control
test log, validates process/token/TLS/hash proofs and creates an exclusive
readiness receipt. Existing receipts and logs cannot be overwritten. Preserve
previous proofs before requalification; never mark stale checks PASS manually.

## Browser sandbox and TLS

The pinned browser-manager extension replaces Crawl4AI's insecure launch
defaults; it uses dedicated mode and explicitly sets Playwright
`chromium_sandbox=True`. Contexts use `ignore_https_errors=False`. Both requested
and actual process arguments are checked for sandbox, certificate and origin
policy bypasses. [Playwright's launch API](https://playwright.dev/python/docs/api/class-browsertype)
documents the explicit sandbox option.

Readiness also requires actual renderer-token inspection: integrity at most
Low (RID 4096) and a restricted token or AppContainer, plus verified parent
Job membership for worker and browser processes. This follows the Windows
[Chromium sandbox diagnostics](https://www.chromium.org/Home/chromium-security/articles/chrome-sandbox-diagnostics-for-windows/).
The browser broker retains local-user privileges; renderer sandbox proof is
not a claim that the broker is an AppContainer. Uninspectable tokens block
readiness. No elevated or sandbox-disabled fallback is provided.

The same strict context must reject a throwaway self-signed localhost TLS
fixture with a certificate error. That exact worker-owned URL is allowed only
inside a diagnostic operation. A valid public HTTPS probe must also succeed.
Certificate errors have their own failure code and cannot become no-event proof.

## Controls and limitations

| Control | Bound | Status |
| --- | --- | --- |
| Host wall time | 30 seconds | Enforced; kills containing Job |
| Navigation | 15 seconds | Enforced by adapter |
| Concurrent dynamic jobs | 1 per common repository | Enforced by native-safe process lock |
| Retries / calls per research action | 0 / 1 | Enforced in action-bound adapter |
| Job committed memory | 2 GiB aggregate | Enforced, queried back |
| Job active processes | 32 | Enforced, queried back |
| Job CPU rate | 50% hard cap | Enforced, queried back |
| stdout / stderr | 2 MB / 64 KiB | Enforced; overflow stops Job |
| rendered HTML / extracted text | 750 KB each | Enforced before response |
| Temporary storage | 64 MB observed threshold | Monitored and terminated; not an OS disk quota |
| Cleanup | Success, failure and timeout | Job termination/kill-on-close, zero-active readback, workspace removal |

The Job disallows breakaway. Descendant membership is checked during rendering.
Windows [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
provide ownership and resource controls, not a standalone filesystem sandbox.
Private profiles/cache/temp directories are deleted after each call. Output
limits bound each capture; archived diagnostics accumulate until operator
retention, and no global archive disk quota is claimed. Crash-created artifacts
or inaccessible cleanup are explicit failures. No browser daemon is retained.

Only public HTTPS port 443 without credentials is accepted for acquisition.
DNS must resolve exclusively to public addresses; one target address is pinned
in browser resolver rules, and unknown external DNS is denied. Navigation and
subresource routes permit only the requested hostname. Cross-origin redirects,
private/local addresses, dangerous schemes, downloads, service workers and
WebSockets are rejected. A JS page depending on other domains may fail under
this deliberately narrow role. These are adapter controls, not a machine-wide
egress firewall. No arbitrary user scripts, file retrieval or browser actions
are accepted by the request protocol.

## Failure and provenance contract

`SOURCE_DYNAMIC_ROUTE_REQUIRED` remains the static extractor's signal.
It is never used to hide a failed dynamic backend. The backend distinguishes:

- `SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE`: registration proof unavailable/stale.
- `DYNAMIC_BACKEND_UNAVAILABLE`: runtime/package incompatibility or absence.
- `DYNAMIC_BACKEND_READINESS_FAILURE` / `DYNAMIC_READINESS_FAILURE`: startup,
  containment, renderer or TLS readiness proof failed.
- `DYNAMIC_LAUNCH_FAILURE`, `DYNAMIC_NAVIGATION_TIMEOUT`, `DYNAMIC_TLS_FAILURE`,
  `DYNAMIC_PAGE_RETRIEVAL_FAILURE`, `DYNAMIC_BROWSER_CRASH`.
- `DYNAMIC_EXTRACTION_FAILURE`, `DYNAMIC_NORMALIZATION_FAILURE`.
- `DYNAMIC_POLICY_REJECTED`, `DYNAMIC_CONCURRENCY_LIMIT`,
  `DYNAMIC_OUTPUT_LIMIT`, `DYNAMIC_STORAGE_LIMIT`, `DYNAMIC_CLEANUP_FAILURE`.

Each dispatched attempt preserves request, raw structured response, host
execution receipt and validation outcome. Successful normalized sources retain
requested/final URL, redirects, retrieval timestamp, navigation status,
backend/version, rendered and text hashes, normalized output hash, extraction
status and action/parent lineage. Probe captures carry a diagnostic marker and
do not enter candidate/evidence or story generation.

Implementation: `browser_protocol.py`, `browser_windows.py`,
`browser_worker.py`, `dynamic_browser.py`, the existing discovery fallback and
executor binding. Controls are covered by `tests/test_v5_dynamic_browser.py`;
public/runtime token proof is captured separately from network-free tests.
