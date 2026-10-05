# DRAGON repository reconciliation — 2026-10-05

This is a development repository cutover audit. It is not the production
activation in [LOCAL-CUTOVER.md](LOCAL-CUTOVER.md). No scheduler, legacy fallback,
evidence gate, research budget or production provider promotion is changed.

## Baseline and selection

- Original remote `main`: `f55b2b8d277325ca18f2201b7783b2e97c858401`.
- Original local `main`: `1099b32642f92ba5d1d476deceb19e8434084d15`.
- Original primary checkout: `codex/dragon-ultimate-migration`,
  `cd95120d79c3a760a70f894575760c903182e920`.
- Selected latest code: `codex/hard-lane-research-completion`,
  `3b86f1d3c3907c596ef01a31c3c8075f2c609ee2`.
- Canonical branch: `codex/dragon-v5-cutover`, in a new managed worktree.
- Merge milestone: `3b9ef0ec340d61a0f480915b51174f80a4f830bb`, parents are
  the selected code and original remote `main`. No merge conflicts occurred.

The selected code contains every local branch tip by Git ancestry, not merely
by timestamps. Its merge base with remote `main` is
`3f75f4bd1005a5932c603a8a786027bcf94b1f01`. The three remote-only commits
`40b8440`, `192091f`, `f55b2b8` contain explicitly labelled cutover fixture
archives. They were merged intact. No daily-run or edition bytes differ from
remote `main` in the canonical tree (`git diff --quiet origin/main HEAD --
daily-runs editions` passed after the merge).

## Local lineage map

All 14 pre-existing local branches and all eight attached worktrees were
inspected. The new integration worktree is the ninth. For the rows below,
the tip is also the merge base with the selected code, and the count of commits
unique relative to the selected code is zero. This is why no cherry-picking or
blind worktree merging was required.

| Branch / tip | Worktree or role | Important contained work | Integration disposition |
| --- | --- | --- | --- |
| `main` / `1099b32` | Local base branch | Early V5 orchestrator/editorial foundations | Contained; local ref preserved |
| `codex/dragon-ultimate-migration` / `cd95120` | Primary checkout | `1701ac8` hard semantic breadth; artifact/issuer/current-event repairs | Contained; dirty primary left untouched |
| `codex/phase2-research-acceptance` / `6c88778` | phase2-research-acceptance worktree | Fresh isolated research acceptance boundary | Contained; retain local trial artifacts |
| `codex/provider-research-sep26` / `295786b` | provider-research-sep26 worktree | Exact provider artifact routing | Contained; retain local trial artifacts |
| `codex/provider-exact-live-retest` / `b8b4ffe` | provider-exact-live-retest worktree | Hard target injection/discovery contract | Contained; retain local trial artifacts |
| `codex/provider-hard-deficit-live-20260926` / `b8b4ffe` | Duplicate tip | Same provider targeting | Superseded duplicate recovery ref |
| `codex/provider-retargeting-live-20260927` / `b8b4ffe` | Duplicate tip | Same targeting; missing historical evidence remains missing | Superseded duplicate recovery ref |
| `codex/provider-retargeting-deficit-repair-20260929` / `a26661d` | provider-retargeting-deficit-repair worktree | Deficit route scheduling | Contained; clean checkout |
| `codex/hard-lane-yield` / `f8210a8` | hard-lane-yield worktree | Required dispositions/reservations, archive/replay, exhausted allowance behavior | Contained; retain artifacts |
| `codex/provider-schema-live` / `662113a` | provider-schema-live worktree | Prepared schema preflight, historical waiver | Contained; retain artifacts |
| `codex/contract-fault-isolation` / `251a82e` | Recovery branch | Contract fault isolation/shared action identities | Contained |
| `codex/live-retrieval-acceptance` / `db21fc0` | Recovery branch | Bounded provider-free acquisition and observed issuer/document provenance | Contained |
| `codex/verified-no-event-finality` / `6b38c70` | Recovery branch | Six-state strict bounded research-finality proof | Contained |
| `codex/hard-lane-research-completion` / `3b86f1d` | contract-fault-isolation worktree | Mandatory ladders, carried identities, dynamic recovery, qualified Windows adapter | Canonical code ancestor |

The two clue commits were verified as exact ancestors:
`1701ac8ae4622127ec01d196540c6d563efd1a67` and
`295786b96e8b03d113fb958af439d373b25c0cb6`.
Notable later implementation milestones include `b8b4ffe`, `a26661d`,
`e2cffd6`, `2090cf4`, `9c1e408`, `0388107`, `db21fc0`, `b15cc21`,
`7ec8a34`, `076b1f9`, `4a08d1d`, `58f10d0` and `1e87515`.
All provenance commits are preserved; no squash/rebase/force update is used.

Reflogs were inspected where useful. No stashes existed. One remote (`origin`)
was configured. Remote development branches were `fix/automatic-publication`,
`codex/implement-stage-5-and-stage-6-for-dragon-project`, and
`codex/run-stage-6-correction-in-codex-cloud`; their tips are already ancestors
of canonical code. GitHub PRs #1, #2 and #3 were confirmed merged/closed, with
no open PR before this reconciliation. They can be considered for later
cleanup; this task deletes no branches or worktrees.

## Excluded work and preservation

The only commits returned by `git log --all --not` the selected tip were the
three remote archive commits and `d7f872b` / `551edf5`. The latter are retained
worktree snapshot commits containing 15 and 36 trial-artifact files, respectively,
not a missing source implementation. Their recovery refs/objects remain; they
are intentionally excluded from the canonical source branch. No new live raw
packet, trial tree, local credentials or browser proof is committed.

The primary checkout had one tracked SearXNG launcher edit, its untracked backup,
and 3,573 untracked files. Other worktrees had 106, 18, 15, 36, 36, 0 and 29
untracked files, respectively. Each file received a path/size/SHA-256 preservation
inventory outside the worktrees before edits. The primary launcher change is a
valid Windows PowerShell 5 compatibility fix: .NET Framework lacks static
`RandomNumberGenerator.Fill`. Its `Create/GetBytes/Dispose` implementation was
applied independently to the canonical branch without the incidental BOM/trailing
blank line. Native PowerShell syntax and RNG execution passed; the original dirty
file and backup remain untouched. No service restart or secret output was needed.
The final preservation check rehashed all **3,813 inventoried untracked files**
across the eight original worktrees and compared their Git status: PASS, zero
changes. All 17 README local links resolved.

Seven existing sealed bundles verified **595** artifacts:

| Bundle family | Artifact count |
| --- | ---: |
| Original provider acceptance | 67 |
| Original retrieval acceptance | 144 |
| Retrieval evidence review | 93 |
| Research finality review | 43 |
| Two hard-lane completion reviews | 43 + 43 |
| Dynamic browser readiness | 162 |

The original October 4 verdicts stay blocked. September 27 remains
`SEP27_PRIMARY_ARTIFACTS=UNAVAILABLE`, `SEP27_EXACT_REPLAY=NOT_POSSIBLE`,
`HISTORICAL_REPLAY_WAIVED_DUE_TO_MISSING_PRIMARY_ARTIFACTS`. No reconstruction or
substitution was attempted. Sealed evidence is local, hash-bound, and not made
portable merely by mentioning it here.

## Documentation occurrence classification

A tracked-file scan covered Markdown, YAML, JSON, Python, HTML and CSS for old
language, stage, five-job and production-master terminology. It recorded 83
matching files: 35 historical artifact files, seven test/fixture files, one
dated audit file, one current overview and 39 legacy/shared/runtime-context files.
The complete per-line inventory is retained locally as `legacy-occurrences.json`.
These counts describe the scan pattern, not a universal proof of no stale text.

| Class | Examples | Disposition |
| --- | --- | --- |
| A — current authority/overview | README, LOCAL-AUTOMATION, phase status | Reconciled current V5 architecture/status; fixed stale disabled-SearXNG statement |
| B — historical editions/artifacts | dated research, daily-runs, editions, cloud/scheduled tests | Preserved exact bytes and original language |
| C — legacy configuration/tooling | `config/pipeline.yaml`, execution constraints, schedules, `scripts/run_pipeline.py`, V4 publisher/validators | Deprecated as V5 authority; retained for legacy/preproduction compatibility |
| D — tests/fixtures | Darija/language, scheduled workflow, legacy schema expectations | Preserved; no evidence requirements or test expectations weakened |
| E — explanatory history/shared material | migration/repair audits, V4 spec/prompts, shared editorial-depth config | Kept version-scoped; labels/index distinguish dated baseline from current evidence |

`SPEC-v1.md` already declares legacy scope. Explicit scope notices were added
to PREPRODUCTION, the Darija/publishing role docs, production-master/manual
publisher, and the scheduled-prompt index. The five actual scheduled prompt
contracts, YAML values and GitHub production workflow behavior are unchanged.
Some shared editorial-depth configuration is still consumed by V5; it is not
obsolete merely because a legacy-language string exists there. The README and
authoritative V5 spec remain the obvious current entry points.

The September Definition-of-Done/test/readiness ledgers retain their original
observations and receive a baseline scope notice. The current phase register
is updated separately; it no longer mislabels all later implemented foundations
as NOT_STARTED or claims to mirror an external active Goal.

## Validation

Environment: Windows 11 build 26300, CPython 3.14.5 (MSC 1944, AMD64),
pytest 9.0.3, Pillow 12.2.0, pypdf 6.14.2, PyYAML 6.0.3, jsonschema 4.26.0,
WeasyPrint 68.1, Trafilatura 2.2.0, arabic-reshaper 3.0.1, python-bidi 0.6.10.
The local EPUBCheck 5.3.0 JAR was supplied through `DRAGON_EPUBCHECK_JAR`.

```text
python -m pytest -q -p no:cacheprovider tests/test_v5_provider_targeting.py tests/test_v5_provider_exact_routing.py tests/test_v5_hard_lane_completion.py tests/test_v5_research_finality.py tests/test_v5_dynamic_browser.py tests/test_v5_archive.py tests/test_v5_state.py tests/test_v5_current_event_coverage_recovery.py tests/test_v5_evidence_qualification_regression.py
```

Targeted code regression: **185 passed, 0 failed, 0 skipped** (36.12 seconds).

```text
python -m pytest -q -p no:cacheprovider --junitxml=<local evidence root>/full-suite.xml
```

Integrated-code full baseline: **994 passed, 0 failed, 2 skipped** (234.55
seconds). Both skips are existing Windows WeasyPrint native-library cases in
`tests/test_automatic_publication.py`; their Linux CI path is retained.

The initial PR Linux CI run `37344894007` exposed stale verification setup:
`unittest discover` ran 190 cases with 27 import errors because pytest was not
installed, and would not discover the newer pytest functions. The minimal CI
repair installs pytest 9.0.3 as a test-only dependency and invokes the complete
suite with pytest, preserving `DRAGON_RENDER_SMOKE=1` and all native rendering
cases. No test expectations, production workflow or runtime dependency changed.
The final CI status is recorded on the reconciliation PR.
The corrected runner command was also exercised locally: **994 passed, 0 failed,
2 skipped** in 319.40 seconds (`ci-equivalent-windows.xml`). The two native-library
smoke cases remain unavailable on this Windows host and stay enabled in Linux CI;
this local result does not substitute for the required Linux check.

The complete Linux run `37374456131` then reported **969 passed, 13 failed,
14 skipped** (153.42 seconds). It exposed previously hidden fixture assumptions:
seven acceptance cases require a real `codex/` development branch but Actions
checks out a detached merge; three proof-registration cases assumed a Windows
host; three PDF cases passed placeholder HTML which WeasyPrint correctly rendered
literally. CI now creates an ephemeral local `codex/ci-verification` branch at the
unchanged checked-out commit. This creates no remote branch, changes no ancestry,
and preserves the actual development-branch acceptance guard.

Proof fixtures explicitly simulate only the dynamic-browser module's Windows host
boundary without changing the runner OS; all existing assertions and native
integration skips remain. An additional negative test proves non-Windows hosts
still cannot register Windows containment. PDF fixtures now call the actual Arabic
HTML builder instead of supplying empty/`x` documents, including the blank-page
failure injection case. Pagination, Arabic extraction, cover identity, determinism,
source links, visual QA and blank-page assertions are unchanged. No rendering,
containment or editorial runtime gate is relaxed. Final platform regression and
corrected Actions results are recorded on PR #4 and the task report.
The targeted acceptance/archive/browser/publication regression after fixture
correction passed **101 tests** (55.47 seconds).
The final full Windows regression passed **995 tests, 0 failed, 2 skipped** in
307.49 seconds (`cross-platform-final-windows.xml`); the count increases by the
new negative containment test. Linux native rendering cases remain enabled.

The documentation contract check initially had one failure because the rewritten
README omitted the existing tested phrase “V5 is the authoritative implementation
target.” That truthful marker was restored; tests were not changed. The immediate
contract/scheduled regression then passed 23 tests. The final full regression
passed **994 tests, 0 failed, 2 skipped** in 303.30 seconds, recorded separately
in `full-suite-final.xml`. No test expectations were modified.
Final documentation regression (`test_v5_contract`, `test_scheduled_workflow_contract`,
`test_v5_runbooks`, `test_v5_dod_traceability`, `test_v5_component_matrix`) passed
**29 tests**. An initial command using nonexistent test filenames ran zero tests;
the corrected command used the actual repository files.

Other commands: `python scripts/validate_configuration.py` PASS (V4 retained
five-job contract), `python scripts/auto_publish.py --check` returned `[]`
(read-only, no edition publication), `load_local_config` PASS (V5, 26 stages,
one disabled Codex scheduler), `python -m compileall -q dragon scripts
dragon_daily.py dragon_watchdog.py` PASS, `git diff --check` PASS.
`python dragon_browser_readiness.py status` returned `DYNAMIC_ADAPTER_READY` on
this host. `python dragon_acceptance.py` correctly returned BLOCKED/exit 1:
production edition/reviews/unattended dates/provider promotion and activation
evidence remain missing. The new worktree does not contain prior host-local
synthetic artifacts; their absence is not rewritten as an earlier failed trial.

## Fresh bounded live research

The user explicitly authorized one provider/network acceptance in the
reconciliation request. This does not activate an automation or permit article,
cover, rendering, archive or delivery stages.

```text
python dragon_acceptance_bundle.py prove --archive-root <local evidence root>
python dragon_provider_research_acceptance.py --date 2026-10-05 --technical-validation --authorize-provider-research --archive-root <local evidence root>
```

The provider-free durability proof PASS is bound to the merge milestone,
including actual source deletion, discovery and tamper/overwrite/missing-required
failure injections. The fresh trial is separately sealed under shared Git
storage, not committed as an edition. Technical validation is required because
the real Casablanca deadline had already passed; no clock override or backdate
is used. Preflight confirms ChatGPT Codex authentication, live SearXNG results,
prepared schema/payload, one provider-call limit and zero provider retries.
Existing eight-action/two-epoch research limits are unchanged.

Fresh run identity: `provider-research-acceptance-ed18957d-2df6-482b-9e65-b44e5a023cf8`.

**Result: `RESEARCH_RECOVERY_REQUIRED`, exit 1.** The first seven research stages
completed; research recovery failed its acceptance gate at attempt one. Article
generation and publication stages did not run. `NORMALIZED` describes the provider
packet, not publication acceptance. There was exactly **one provider call, zero
provider retries**, returning 27 source records and 23 section plans. The deadline
was `MISSED`; on-time acceptance is inapplicable to this technical trial.

Actual `provider-research/request.json` contains unresolved mandatory hard targets
`HARD:ACCOUNTABILITY` and `HARD:SERVICE` in `research_targeting`. The captured
prepared prompt includes the targets, exclusions, current/future operation guidance
and `DISCOVERY_INTELLIGENCE_ONLY` warnings. Schema, payload and prompt identities
were captured before invocation. Both raw hard-target dispositions were
`CANDIDATES_PRODUCED`, with three provider-reported search attempts each; those
self-reports are not independently observed native actions.

Native execution used **16 actions: eight per epoch, 13 URL fetches and three
SearXNG searches**. The first epoch reserved seven hard-lane actions and one
general discovery action; the second used eight hard-lane child fetches. No budget
was increased and no second provider call occurred. The action identities below
are execution records, not an assertion that every result qualified as evidence.

| Epoch | Lane | Action identities | Outcome |
| --- | --- | --- | --- |
| 0 | ACCOUNTABILITY | `ACT-0D26A8B1246E`, `ACT-ECBE75E0E7FF` | Provider exact primary/independent URL fetches |
| 0 | ACCOUNTABILITY | `ACT-A16394ED2F88`, `ACT-9E2660B67AF7` | Native SearXNG searches |
| 0 | SERVICE | `ACT-D153598A8177`, `ACT-8658346A92B5` | Provider exact primary/independent URL fetches |
| 0 | SERVICE | `ACT-318ACC4BA760` | Native SearXNG search |
| 0 | GENERAL | `ACT-75B045B99ED4` | One discovery URL fetch |
| 1 | ACCOUNTABILITY | `ACT-A3B975CADB7B`, `ACT-1C04E5CEFF40`, `ACT-202E9B378D12`, `ACT-39DEE9125562` | Four child URL fetches |
| 1 | SERVICE | `ACT-1E5304B10F33`, `ACT-3ADB0E72B48E`, `ACT-51ABA660848B`, `ACT-5FC48B505F94` | Four child URL fetches |

All 13 fetches produced extracted pages, with zero transport/extraction failures.
Searches produced 18 unfetched leads. Of 31 observations, 30 remained extracted,
unverified leads and one was marked potential evidence with `VALIDATED_EVIDENCE`.
That independent-source observation also retained a role-unresolved post-fetch
qualification marker: telemetry reconciliation remains a follow-up; it did not
close either hard lane. Neither ordinary transport success nor that marker is
treated as an accepted PRIMARY evidence bundle.

| Lane | Finality | Mandatory search accounting | Remaining evidence disposition |
| --- | --- | --- | --- |
| ACCOUNTABILITY | `BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH` | 18 required, eight executed, 10 missing | Zero validated events; 10 uninspected leads, eight pending events. Routine Itrane merger notice semantically rejected; second candidate quarantined for missing independent linkage. |
| SERVICE | `BLOCKED_BUDGET_BEFORE_REQUIRED_SEARCH` | 15 required, seven executed, eight missing | Zero validated events; eight uninspected leads, three pending candidates, four pending events. Calendar candidate qualification unresolved; second candidate quarantined for missing independent linkage. |

Both closure reasons are `SEARCH_CUT_SHORT_BY_CAPACITY`. These are pending searches,
not verified absence of events. The remaining recovery needs are the two hard
breadth needs `BREADTH:accountability_and_service:1` and `:2`. Epoch deferral records
numbered 50 and 12; these are records, not 62 unique actions.

Exact discovery was followed by real acquisition: the Competition Council Itrane
notice and Education Ministry calendar were fetched through `PROVIDER_EXACT_SOURCE`;
the Court of Accounts child page was fetched through search discovery. The notice
did not establish substantive oversight; the calendar retained unresolved source
identity/current-operation qualification (`NO_EXPLICIT_ACTIVE_WINDOW`); the court
page described a September conference. None established an accepted current hard
bundle. Direct fetches have no separate numeric exact-match score: N/A, not an
invented score. The default route and native SearXNG fallback were observed; no
dynamic browser action ran in this fresh trial. Host browser readiness is a separate
proof. Query relevance and pending candidate dispositions remain engineering work.

The new bundle sealed **92 artifacts**. Its manifest SHA-256 is
`87bf156fb517182897dcd8ddc88a70bbc79a2c5a5e41a312769bfa837b5399f7`;
raw response SHA-256 is
`eda9bbdaaca09d113d8e9bfa5939127ae3143b1e15600e16e68731b1ba65bb4a`.
`dragon_acceptance_bundle.py verify --bundle <fresh bundle>` PASS independently
checked the manifest and artifacts. Bundle `COMPLETE` means archive completeness,
never newspaper publication completeness.

A guarded offline replay with socket connection methods disabled passed with zero
provider/network calls: normalization, hard target dispositions, candidate
classification, planning, action materialization, scheduling and budget accounting
for both epochs. It reproduces those decisions; it is not a second live retrieval
or whole-publication acceptance. The full new evidence root is local shared Git
storage `.git/dragon/reconciliation-2026-10-05`, separate from historical bundles.

## Synchronization and rollback

GitHub connector access identifies the owner with repository admin/push rights.
The GitHub CLI lacks a separate login, but normal Git credential-manager access
passed a non-mutating push dry-run. Final branch push/read-back, PR inspection
and normal merge must use the final tested head. No force push, squash or
fabricated ancestry is permitted.

Repository rollback uses a reviewed normal revert of the integration merge or
follow-up commit. Runtime activation rollback remains the separate V4 restoration
procedure in LOCAL-CUTOVER. No production schedules are altered here. Retain
recovery branches and artifact-bearing worktrees until their local evidence has
an independently verified durable preservation plan.

The final PR/commit/main identities are recorded by the GitHub PR and task final
report, avoiding a self-referential commit hash in this file.
