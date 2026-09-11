# Final cutover prerequisites — 2026-09-11

## Scope and safety boundary

This report covers deterministic scheduler and Git archive prerequisites only.
It made no editorial-provider call, consumed no provider trial, created no
human-review evidence, and did not alter failed-trial artifacts.  Fixture
evidence is explicitly classified as **not a newspaper** and is never used as
real publication evidence.

## Scheduler architecture and current state

V5 has one supported production scheduler architecture:

```
one Codex local automation
  -> python dragon_watchdog.py
  -> one lock-owning dragon_daily.py process
  -> dependency-driven V5 stages
```

The canonical daily command is `python dragon_watchdog.py` in the saved local
project.  It resolves the edition date in `Africa/Casablanca`; the watchdog
starts a missing run, resumes only safely abandoned work, treats live owners
as non-duplicable, and returns `NO_ACTION` for an already complete run.

Before this work, the repository declared one `codex-local-automation` entry
but intentionally had `scheduler.enabled: false`, cutover scheduler activation
false, and no local Codex automation inventory.  This was not an incomplete
Windows Task Scheduler implementation: V5 expressly prohibits Windows Task
Scheduler, cron, launchd, systemd, GitHub scheduled production workflows, and
backup schedules.

One paused, auditable local Codex automation has now been created:

| Field | Observed value |
| --- | --- |
| Automation ID | `dragon-v5-daily-newspaper` |
| Saved project ID | `dffe397e-c837-49e4-9444-e51c2a4b84fc` |
| Name | `DRAGON V5 Daily Newspaper` |
| Environment | local project working directory |
| Trigger | daily 07:00 (`FREQ=DAILY;BYHOUR=7;BYMINUTE=0`) |
| Status | `PAUSED` |
| Canonical command | `python dragon_watchdog.py` |

The local Codex automation directory contained no DRAGON automation before
creation and contains this one afterward.  The only Windows task matching a
DRAGON name is `Dragon Telegram Incremental Forward`; it is unrelated and is
not a V5 production scheduler.  The V4 fallback/schedules remain preserved by
contract and were not disabled or rewritten.  Their external ChatGPT inventory
is not available from this host, so this report makes no claim that they were
removed.

The automation is deliberately paused.  `docs/LOCAL-CUTOVER.md` allows
activation only after an audit reaches `READY_FOR_CUTOVER`; activating it now
would violate the build-behind and no-live-provider boundaries.  Repository
configuration therefore remains truthful (`scheduler.enabled: false` and V4
fallback enabled).  This is scheduler configuration and installation proof,
not an active-production scheduler trial.

## Provider-free scheduler smoke proof

`dragon_watchdog.py` now supports `--synthetic --date YYYY-MM-DD` only for an
explicit deterministic smoke.  The production automation never uses the flag.
The final-revision smoke executed:

```
python dragon_watchdog.py --synthetic --date 2099-04-02
```

It recorded `trigger: watchdog`, acquired the run lock, created state for run
`eeafa884-cb56-4b0d-beee-fbc29fc170e4`, completed 21 stages, produced a local
synthetic publication, and left archive/delivery as `DEGRADED` because
synthetic mode disables external side effects.  It used runtime fingerprint
`718697850018665a1294959478c73085ee7b85383771a019e79958c634566b4e`.
A second identical watchdog command recorded `NO_ACTION`, created no duplicate
edition, and launched no second process.

| Evidence | SHA-256 |
| --- | --- |
| `daily-runs/2099-04-02/state.json` | `e13b51e29ab986d6de083fa2ccae3d44ae4737461d1f997b5f748a64f56c2c20` |
| `daily-runs/2099-04-02/recovery/watchdog-latest.json` | `e65ed45f8c5d524e05fcaa9632cdf376de7e4c317b48990277e30287f41f3d25` |
| `daily-runs/2099-04-02/run-report.json` | `62b3410b65aaa3627fff05f2eafe049aff4f5ff8ec8c938e702da3429f1ac65b` |

## GitHub archive and remote read-back proof

`GitArchiveProvider` was hardened to require either the exact dated edition
path or an explicit `fixture=True` path below `acceptance/cutover-fixtures/`.
It rejects zero-byte artifacts and rejects an existing archive directory when
the remote file set or bytes differ.  This prevents wrong-date/path archives
and historical archive mutation while retaining exact-byte idempotent retries.

`dragon_archive_fixture_check.py` clones the configured real GitHub `main`
branch into a temporary directory, writes a valid text/PDF/EPUB/cover/manifest
fixture only under the dedicated fixture namespace, uses the real provider,
then reads every remote Git blob back and hashes it again.  The final proof was
run at source revision `08ec905a086bc98bc26637b437e03220f149dc07`:

| Item | Evidence |
| --- | --- |
| Remote fixture commit | `f55b2b8d277325ca18f2201b7783b2e97c858401` (`archive: DRAGON cutover fixture …`) |
| Fixture path | `acceptance/cutover-fixtures/2026-09-11/20260911T005423+0100-e84f04ef025e` |
| First archive | `COMPLETE`, local and remote commit identical, exact-byte verified |
| Retry | `COMPLETE`, `ALREADY_COMMITTED`, same commit |
| Machine receipt | `acceptance/machine/github-archive-fixture/20260911T005423+0100-e84f04ef025e/receipt.json` |
| Receipt SHA-256 | `370b14c0f1101e7057b8a7bac66b719226969a2eba9d303fa86fb62854f9f68f` |

Artifact hashes in the receipt prove the remote bytes for the fixture text,
representative PDF, EPUB, canonical cover, fixture status, and manifest.  The
PDF hash is `d11443b3868f3d88e5f091426ab9a0b6c402329fb79147aad507d267fe993866`;
the EPUB hash is `b562357a50f6590e1c71d8a666c1077e8e714c19604ef136b6f6b9c74b4df9b4`;
the cover hash is `2573079b2fe9f13f86df23dfa72abb3a9107414bd6610b7bd2dd3f3b7c2f6db8`.

An earlier fixture attempt detected Windows CRLF-versus-Git-LF mismatch during
read-back and failed safely.  It remains in the same clearly labelled fixture
namespace; the generator now writes deterministic LF bytes and the final
proof above passed.

## Negative and regression evidence

The deterministic archive tests cover wrong canonical date/path, a
zero-byte artifact, a stale/concurrent remote, corrupted/mismatched remote
bytes, crash-after-local-commit recovery, exact read-back, idempotent retry,
and attempted historical mutation.  Acceptance tests continue to reject
mismatched manifest/receipt hashes.  Watchdog tests cover Casablanca midnight,
exclusive locking, dead-owner recovery, stale live-owner safety, duplicate
invocation, and the explicit synthetic launch path.

| Validation | Result |
| --- | --- |
| Focused archive, watchdog, scheduler, and acceptance suite | 37 passed |
| Full repository suite | 345 passed, 2 expected skips |
| Hash-bound chaos/finality suite | PASS; 139 observed tests, every scenario PASS |
| Chaos JUnit SHA-256 | `9a1a064252b2bc36b3779de700b440269daf362c7e480c4087e01df71440d9b2` |
| Previous all-no-news and one-lead research protections | included and PASS |
| 2026-09-10 / 2026-09-11 article-repair regressions | included and PASS |

## Final audit and blocker matrix

The real `python dragon_acceptance.py` audit remains `BLOCKED`, as it must.
Fixture evidence does not satisfy production evidence gates.

| Gate | State | Exact reason/evidence |
| --- | --- | --- |
| Local synthetic fixtures | PASS | watchdog smoke completed local publication; full fixture tests pass |
| Arabic PDF / EPUB fixture QA | PASS | full suite and synthetic smoke pass; external effects remain disabled |
| Chaos / finality / resume | PASS | 139-scenario receipt and JUnit above |
| Research sufficiency / repair protection | PASS | prior regressions remain in the green full suite |
| V5 scheduler configuration | PASS | one installed paused Codex automation, canonical watchdog contract verified |
| V5 scheduler active-production evidence | BLOCKED | activation is prohibited until `READY_FOR_CUTOVER`; no fabricated scheduler review |
| GitHub fixture archive | PASS | real GitHub commit, blob read-back, exact hashes, idempotent retry |
| Production GitHub archive receipt | BLOCKED | a real completed production edition is required; fixture receipt is not promoted |
| Real live publication | PENDING_AUTHORIZATION | requires separately authorized live provider trial |
| Human review | PENDING_VALID_LIVE_PUBLICATION | cannot be manufactured |
| V4 retirement / competing GitHub production disablement | BLOCKED | contract requires acceptance evidence before cutover |

Another live provider trial is the next logical *evidence* step only after a
separate human authorization.  If it creates a valid real edition and human
review, the remaining cutover sequence must still follow `LOCAL-CUTOVER.md`:
obtain the required real archive and scheduler observations, then activate the
paused automation only once the audit permits it.  No provider has been
promoted and production is not marked complete.

NOT_READY_FOR_FINAL_LIVE_AUTHORIZATION
