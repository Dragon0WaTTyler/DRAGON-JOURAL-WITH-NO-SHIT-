# Dynamic browser backend readiness acceptance

## A. Baseline

Accepted baseline `f8cb36ce`, branch `codex/hard-lane-research-completion`,
Windows production Python 3.14.5; accepted suite 927 passed, 2 skipped.
Accepted worktree: `C:\Users\walid\.codex\worktrees\contract-fault-isolation\dragon journal with no shit`.
The prior readiness bundle `hard-lane-live-preflight-1aefa8ab-0e57-46e0-af2c-439c7370069f`
remains unchanged. Scheduler, recovery budgets, finality ontology and publication
gates were preserved.

## B. Exact source of unsafe arguments

Crawl4AI 0.9.4 constructs unconditional `--no-sandbox`,
`--ignore-certificate-errors` and SPKI certificate bypass defaults in both its
managed and dedicated launch builders. Context `ignore_https_errors=False`
does not remove these process arguments. Playwright independently disables the
Chromium sandbox unless explicitly enabled. Its headless defaults also enable
unsafe SwiftShader and disable DevTools self-XSS warnings.

The pinned browser-manager extension replaces the Crawl4AI launch options;
Playwright defaults are filtered and actual arguments are checked.
The browser mode must be dedicated: builtin mode selects the managed path.
Windows changes channel selection, not the unsafe defaults.

Sources and ownership: [root-cause note](DYNAMIC-BROWSER-ROOT-CAUSE.md).
Implementation: [launch policy](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_protocol.py:40>),
[SecureBrowserManager](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_worker.py:77>).
Tests: [unsafe flag and TLS/sandbox rejection](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:65>).

## C. Python 3.14 / 3.13 integration

Production imports no Crawl4AI package. It invokes a native isolated CPython
3.13.14 worker using a fixed argument list, isolated imports, structured JSON,
bounded pipes, exit status and stderr capture. The official embeddable ZIP was
verified against SHA-256
`90b4e5b9898b72d744650524bff92377c367f44bd5fbd09e3148656c080ad907`.
A fixed, hash-bound _pth file reuses the existing cp313 Crawl4AI packages.

The Store venv activated its real interpreter outside the parent Job; suspended
wrapper assignment was insufficient and self-join failed. It is not qualified.
Production Python was not changed or given new browser dependencies.

Implementation: [run_worker](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/dynamic_browser.py:53>),
[worker protocol](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_worker.py:243>),
[join_parent_job](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_windows.py:217>).
Tests: [structured normalization](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:50>),
[native worker membership](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:258>).
Evidence: runtime-proof.json and browser-proof/attempts in the durable bundle.

## D. Sandbox / isolation result

PASS for Playwright Chromium 153.0.8010.12, executable
`C:\Users\walid\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe`.
Sandbox=True is explicit. Actual worker/browser tree membership and renderer
tokens were inspected. Renderer tokens were restricted at Untrusted integrity
(RID 0). Job membership passed and cleanup readback showed zero active processes.

The tested Edge 154.0.4258.53 path was rejected because its WinRT App ID service
was outside the parent Job. The final backend uses the existing Chromium stack.
The broker retains local-user privileges; this is not a broker AppContainer or
whole-filesystem isolation claim. Earlier probes/receipts are preserved and
superseded by the final proof, including the added unsafe-headless checks.

Implementation: [WindowsJob and token_security](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_windows.py:72>),
[actual process proof validation](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon_browser_readiness.py:100>).
Tests: [token observation](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:193>),
[reject incomplete actual proof](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:224>).
Evidence: manual-proof-audit.json, successful_proofs[0].

## E. TLS result

PASS. The final public HTTPS target returned 200 with strict context TLS and no
certificate bypass arguments. A throwaway self-signed certificate was rejected
in the same browser context with `ERR_CERT_AUTHORITY_INVALID`.
Certificate failure remains `DYNAMIC_TLS_FAILURE`.

Implementation: [strict context and TLS fixture](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_worker.py:23>),
[classify_error](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_protocol.py:75>).
Tests: [sandbox/TLS intent](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:75>),
[explicit failure classification](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:97>),
[reject invalid TLS proof](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:224>).
Evidence: manual-proof-audit.json, tls_negative and effective_arguments.

## F. Resource bounds

Enforced: 30-second host wall limit, 15-second navigation limit, concurrency 1,
retries 0, one dynamic call per research action; Job memory 2 GiB, processes 32,
CPU hard cap 50%, no breakaway, kill-on-close. stdout 2 MB, stderr 64 KiB,
rendered HTML and extracted text each 750 KB. Temporary storage has a monitored
64 MB termination threshold; it is not an OS disk quota. Archive retention has
no global disk quota. Success, failure, timeout and output overflow cleanup
are tested with real owned subprocess descendants.

Implementation: [limits](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_protocol.py:18>),
[Job readback/cleanup](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_windows.py:75>),
[bounded runner and action binding](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/dynamic_browser.py:53>).
Tests: [four native cleanup modes](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:167>),
[concurrency](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:118>),
[lineage/single invocation](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:125>).
Evidence: host_job_limits, host_cleanup and workspace removal in the manual audit.

## G. Network / navigation safety

Acquisition accepts public HTTPS port 443 without credentials. Private/local
targets and unsafe schemes are rejected. DNS must resolve exclusively to public
addresses; a target address is pinned and unknown external DNS is denied.
Page routes allow the requested hostname only. Cross-origin navigation,
downloads, service workers and WebSockets are blocked. Diagnostic exceptions
are exact worker-owned loopback fixture URLs, never acquisition input.
This is adapter protection, not a machine-wide egress firewall.

Implementation: [safe_url](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_protocol.py:51>),
[context routes](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_worker.py:88>).
Tests: [unsafe targets/private DNS](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:82>).
Sites depending on other origins may truthfully fail under this role.

## H. Registration / readiness

The frozen global extraction YAML remains byte-identical, SHA-256
`700fd4589c9eb212df0f9230b7f5b8cfefaa346058b972dcdc5264cf1dd1f997`.
Explicit host-local enabled=true is now set in the common Git directory's
dragon/dynamic-browser/runtime.json. It can activate only the native extractor
with all mandatory proofs; arbitrary injected callables retain the original
configuration gate.

Readiness checks actual sandbox/TLS/process proof, normalization, cleanup,
concurrency, output limits, unchanged code/runtime/dependencies and proof hashes.
Receipts expire after 24 hours. Missing/stale/changed proofs refuse registration.
The actual normal production factory and all its member adapters were checked.

Implementation: [readiness](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/dynamic_browser.py:32>),
[local binding](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/dynamic_browser.py:304>),
[factory guard](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/deep_research_executor.py:3149>).
Tests: [every mandatory check](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:149>),
[proof/dependency tampering](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:240>),
[local registration tests](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:270>).

## I. Failure classifications

Backend unavailable/readiness failure, launch, timeout, TLS, retrieval, crash,
extraction, normalization, policy, concurrency, output/storage limits and cleanup
remain distinct. `SOURCE_DYNAMIC_ROUTE_REQUIRED` remains the static-path signal.
Failed browser acquisition creates a captured explicit failure; it cannot
become verified absence. Existing finality treats unresolved required DEAD_END
failures as technical blockers.

Implementation: [classifier](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/browser_protocol.py:75>),
[response/evaluation capture](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/dynamic_browser.py:225>),
[unchanged finality guard](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/research_finality.py:258>).
Tests: [failure classes/capture](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:96>),
[normalization rejection](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:139>),
existing hard-lane technical/contract/budget regression tests.

## J. Offline tests

Final focused browser/backend suite: **67 passed**.
It covers the required success, TLS, timeout, unavailable, launch, cleanup,
concurrency, structured response, hashes, negative readiness and complete-proof
checks. Normal tests use mocks or local owned processes; no external network is
required. Arabic JavaScript and self-signed TLS fixtures were also exercised
through the actual adapter in a separate local operational probe.

Logs: focused-hardened-controls.log and offline-hardened-smoke.log.
Test implementation: [test_v5_dynamic_browser.py](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py>).

## K. Actual-adapter final public smoke

Capture `5f36ab78-eb12-41b2-9424-ec21509e8c92`.
DRAGON fetch/extraction -> configured native adapter -> isolated Crawl4AI ->
Chromium -> strict HTTPS -> extraction -> ordinary normalization -> cleanup.

Target: https://www.python.org/about/
Retrieved: 2026-10-05T16:08:12.804500+00:00.
HTTP 200; **16,962 extracted characters**; `EXTRACTED_NOT_VERIFIED`.
HTML SHA-256:
`cbc83c3c8776b1d17a3790d3aa8cbb1da53ec2150b0902cb10e62ebb7ec86b7f`.
Text SHA-256:
`4d2b60b0a9213d9d027649235d7f566374e9c234635a6da2a91eee9a2bc2edec`.
Normalized SHA-256:
`54439b7ca73fbdfb8c59c69dd4b819ff829614fc7d944ae5d40c4885ea07270a`.

Two public operational smokes occurred in this task: the first was superseded
after the registration repair and unsafe-headless audit; the second is the
authoritative final implementation proof. All 17 local operational attempts,
including rejected launches/containment paths, are preserved. None satisfied a
research need or produced journal evidence.

Implementation: [probe](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon_browser_readiness.py:16>),
[normalization/provenance](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/discovery.py:834>).
Tests: [normalized provenance](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/tests/test_v5_dynamic_browser.py:50>).
Evidence: browser-proof/attempts/<capture>/request.json, response.json,
normalized.json, implementation.json, evaluation.json and probe-summary.json.

## L. Negative readiness

PASS. An isolated unsafe configuration is rejected as
`DYNAMIC_POLICY_REJECTED`; a failed secure-launch proof yields
`SOURCE_DYNAMIC_ADAPTER_UNAVAILABLE / CHECK_SECURE_LAUNCH`.
No actual production configuration was weakened for this test.
Evidence: negative-readiness-qualified.json.
Implementation/tests: launch policy, check_readiness and the negative tests above.

## M. Full regressions

Final relevant suites: **248 passed**.
Final full suite: **994 passed, 2 skipped**, 285.51 seconds.
Superseded logs remain preserved: global activation initially broke frozen
configuration/disabled fixtures; restoring the global hash and using local
proof-gated activation repaired that integration. A later full run had one
archive-test failure caused by changing Git HEAD during the run (the captured
proof recorded 4a08d1d, while its bundle recorded 58f10d0). The isolated test
passed, and a stable rerun passed 992/2 before the two added unsafe-argument
cases. Final hardening and the final full suite both passed without a Git race.

Logs: regression-hardened-tests.log, full-hardened-tests.log; failed logs and
git-race-proof.json/git-race-initialized-manifest.json are retained.

## N. Historical / sealed verification

**503 sealed artifacts across seven bundles**, all original manifest identities,
**135 original source files**, and all **106 files** in the untracked October 4
tree verified unchanged. Three sealed finality/completion replays passed with
socket networking explicitly forbidden, zero provider/network calls and
unchanged historical BLOCKED verdicts. SERVICE remains historically technical;
ACCOUNTABILITY remains historically budget-blocked; four breadth needs remain.
September 27 stays UNAVAILABLE / NOT_POSSIBLE / historical replay waived.

Evidence: historical-before.json, historical-final.json and
sealed-replay-hardened.json. Verification uses the existing
[verify_acceptance_bundle](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/archive.py:198>) and
[replay_completion_review](<C:/Users/walid/.codex/worktrees/contract-fault-isolation/dragon journal with no shit/dragon/hard_lane_completion_acceptance.py:51>).
No sealed input or acceptance fixture was rewritten.

## O. Provider / research count

**Provider research calls: 0. Research actions: 0. Research budget: 0/16.**
No fresh hard-lane acceptance, publication or delivery run started.
Operational diagnostics are explicitly marked outside research. Scheduler
8+8 caps, two epochs, evidence/finality requirements and story budgets were
not changed. Full tests exercised synthetic fixtures only.

## P. Final verdict

**DYNAMIC_BROWSER_BACKEND_READY**.
Actual registration: `DYNAMIC_ADAPTER_READY`, reasons [].
Final receipt verified at 2026-10-05T16:08:49.552853+00:00, SHA-256
`d7bcb3dd0ee3fa20405c320d2c73fe8685d854e4b9a022f50ef324d888396087`.
The receipt expires at the corresponding UTC time on October 6 or sooner if
its code/runtime/dependencies/proofs change.

## Q. Remaining blocker / limitations

No remaining blocker for the qualified Windows/Chromium backend.
Edge and the Store activation wrapper are not qualified; the broker retains
local-user privileges, temporary disk use is monitored, and navigation is
restricted to the target hostname. The hard-lane scheduler's live acceptance
is a separate next task and has not been performed. Backend readiness does not
claim research completion or global production readiness.

## R. Git state

Branch: codex/hard-lane-research-completion. Implementation HEAD 1e87515639fdbe29e5607530883209e1c0ca7d1e.
Only the original untracked daily-runs/2026-10-04/ remains after the report commit.
Primary checkout remains at cd95120d79c3a760a70f894575760c903182e920 with its
original script modification, backup and untracked historical directories.
No push, merge or PR was performed.

## S. Commits

- `7e0120ff12974bf8692a396010b997c85bccfd2c`: audited root cause.
- `4a08d1d302a54fbd52fb3e9d502f768a6b74ef32`: worker, containment, readiness, tests.
- `58f10d0e156be747247d48446881296e2e98ab93`: restore frozen global defaults;
  activate only a native host-local extractor with verified proof.
- `1e87515639fdbe29e5607530883209e1c0ca7d1e`: reject unsafe headless defaults.
- Documentation/report commit is recorded in the final response and sealed
  manifest's source_git_revision.

Durable acceptance bundle:
`C:\Users\walid\Documents\codex project\dragon journal with no shit\.git\dragon\research-acceptance\dynamic-browser-readiness-1791213817443`.
The bundle includes all captures, failure history, readiness proof, source
snapshots, tests, manual audit, hashes and historical verification.
