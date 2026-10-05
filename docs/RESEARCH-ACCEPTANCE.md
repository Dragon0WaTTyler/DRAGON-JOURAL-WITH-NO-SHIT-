# Provider-free research acceptance

`python dragon_research_acceptance.py --date YYYY-MM-DD` creates one new V5
research-only run for the explicit edition date. It is manual and is not a
scheduler entry. It checks a clean development worktree, validates the local
research configuration and private SearXNG response, makes an immutable empty
fresh seed, and runs the existing source-monitoring through research-recovery
stages.

It never calls an editorial provider and cannot reach article generation,
publication, archive, or delivery. A successful research-stage run is reported
as `RESEARCH_EXECUTION_COMPLETE_NOT_PUBLICATION_ACCEPTED`; it is not a
production-readiness verdict. An unresolved recovery is reported honestly as
`RESEARCH_RECOVERY_REQUIRED`.

The command intentionally has no resume, retry, synthetic, historical-seed, or
provider options. Re-run it to create a new identity rather than mutating a
prior acceptance attempt.
