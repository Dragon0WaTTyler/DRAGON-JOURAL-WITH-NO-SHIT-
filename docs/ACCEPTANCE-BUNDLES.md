# Durable research acceptance evidence

`SEP27_EXACT_REPLAY = UNAVAILABLE_MISSING_PRIMARY_ARTIFACTS`

The September 27, 2026 trial's original raw packet and run tree are missing.
Archived transcript excerpts are partial evidence and cannot replace those
primary artifacts. Do not reconstruct or claim an exact replay of that run.

Research acceptance CLI runs require a verified provider-free archival proof
before their one authorized research invocation. These runs retain the normal
research stages and stop before editorial or publication stages.

The default durable destination is `dragon/research-acceptance` inside the
repository's **shared Git directory** (`git rev-parse --git-common-dir`). In an
isolated worktree this directory belongs to the primary repository and survives
worktree deletion. `DRAGON_ACCEPTANCE_ARCHIVE_ROOT` or `--archive-root` can select
another absolute location outside the worktree. The storage contains local
research evidence; it does not publish, push, or archive an edition to GitHub.

From the isolated worktree:

```powershell
python dragon_acceptance_bundle.py prove
python dragon_provider_research_acceptance.py --date YYYY-MM-DD --technical-validation --authorize-provider-research
python dragon_acceptance_bundle.py discover
python dragon_acceptance_bundle.py verify --bundle <durable-run-directory>
python dragon_acceptance_bundle.py replay --bundle <durable-run-directory>
```

The implementation must be committed and clean before the live command. The
proof records the current commit, and acceptance checks it against that commit.
The preflight verifies the private SearXNG runtime, a parsed bounded real query,
provider CLI authentication, archive readiness, and the research-only boundary.
A failed mandatory gate stops before provider invocation.

Each run owns an exclusively created directory. Existing run directories are
never replaced. Its manifest binds the run identity, commit, timestamps, provider
call count, native run artifacts, and frozen configuration to SHA-256 identities.
The manifest has its own hash. Intermediate snapshots are marked `IN_PROGRESS`;
a missing required artifact leaves `INCOMPLETE`. Bundle completion describes
complete preservation of evidence, independently of the research verdict.

Provider requests and raw responses are captured before normalization. Scheduler
allocations are written before execution; the existing research state supplies
their full job inputs. The delta epoch additionally preserves its intermediate
packet and recovery inputs because the final recovered packet replaces them.

Replay verifies all archived bytes, loads the frozen configuration, uses the
recorded normalization timestamp, reconstructs source intelligence and research
planning/materialization, and compares every scheduler selection and deferral.
It invokes no provider, search, or retrieval adapter. Use the implementation commit
named in the manifest. Replay receipts live beside bundles under `replay-reports`
and are bound to the original manifest hash; the completed bundle remains intact.
