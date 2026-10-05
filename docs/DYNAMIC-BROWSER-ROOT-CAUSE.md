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
- Playwright's headless launch also adds `--enable-unsafe-swiftshader`
  (`coreBundle.js` line 43337) and its defaults disable DevTools self-XSS
  warnings (line 34892). The final adapter filters both defaults and rejects
  them in effective arguments. Chromium's own
  [SwiftShader security guidance](https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/swiftshader.md)
  explicitly excludes untrusted content from the unsafe WebGL opt-in.
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

## Integration findings from isolated local probes

- Crawl4AI's `browser_mode="builtin"` forces managed-browser operation in
  `async_configs.py` (line 1027). A channel setting in that mode does not prove
  the executable used. The old smoke's Edge setting is configuration intent;
  it did not record an executable identity. Dedicated mode is needed for the
  browser-manager extension to own the effective Playwright launch options.
- The Microsoft Store Python 3.13 venv wrapper activated its actual interpreter
  outside the parent Windows Job. Assigning the suspended wrapper was
  insufficient. A named Job self-join also failed with access denied. Those
  attempts were rejected and preserved, with no research execution.
- A SHA-256 verified official CPython 3.13.14 embeddable runtime removes that
  activation boundary. It reuses the already installed cp313 Crawl4AI packages
  through a fixed, hash-bound `_pth` file; production Python 3.14 stays separate.
- Actual Edge 154.0.4258.53 ran its worker, browser and renderers inside the Job,
  but its `winrt_app_id.mojom.WinrtAppIdService` process was outside it. That
  probe was also rejected. DRAGON does not claim containment of that Edge path.
- The existing Playwright Chromium runtime passed the local rendered-page,
  process-membership, restricted-renderer-token and invalid-certificate probes.
  This changes the executable within the existing Crawl4AI/Playwright stack;
  it does not add a crawler or an external service. Public readiness remains
  conditional on the actual-adapter HTTPS smoke and all control proofs.
