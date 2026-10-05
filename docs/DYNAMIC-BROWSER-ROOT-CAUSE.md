# Dynamic browser backend root cause

Baseline: f8cb36ce on codex/hard-lane-research-completion.
The previous readiness bundle is immutable and remains separate from this work.

## Effective launch trace

- Crawl4AI 0.9.4 `browser_manager.py` constructs `--no-sandbox`,
  `--ignore-certificate-errors` and `--ignore-certificate-errors-spki-list`
  in both `ManagedBrowser` arguments (lines 73–80) and
  `BrowserManager._build_browser_args` (lines 1092–1099).
  These defaults are unconditional; they do not originate in DRAGON, its
  smoke harness, a browser profile, or Windows detection.
- `BrowserConfig.ignore_https_errors=False` controls browser-context options,
  but does not remove those process arguments. The process-level bypass
  therefore contradicts the configured context intent.
- Playwright's Chromium launcher independently adds `--no-sandbox` unless
  `chromium_sandbox=True` (installed 1.63.0 `coreBundle.js`, lines 43346–43347).
  Removing only Crawl4AI's string would not establish sandboxing.
- Crawl4AI's Windows-specific branch only omits the default chromium channel;
  it does not harden sandbox/TLS settings. Other operating systems receive the
  same unsafe defaults. This task qualifies Windows only.

## Existing DRAGON boundary

`ExtractionFallback` in discovery.py is explicitly injectable.
`discovery_adapter_from_config` requires enabled + integration PASS, and
`_fetch_action_source` uses the fallback only for an explicit DYNAMIC action.
No installed-runtime loader or child-process containment exists at this boundary.
The editorial subprocess pattern supplies structured JSON/exit/timeout handling,
but it does not establish browser descendant cleanup or resource containment.

## Smallest repair and proof required

Keep Crawl4AI, the existing fallback, and isolated Python 3.13. Use a pinned
Crawl4AI browser-manager extension with explicit Playwright sandbox=True,
strict TLS contexts and effective-argument verification. Do not modify installed
dependency files. A structured one-operation worker is contained by Windows
Job Objects, with bounded output, wall time and concurrency. Registration must
require hash-bound readiness evidence, not an import or a YAML PASS string.
The effect on retrieval remains unproven until the new integration tests/smoke.
ADR-007 and research/finality/budget contracts remain unchanged.

