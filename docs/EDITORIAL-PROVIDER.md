# DRAGON V5 local editorial provider protocol

The production orchestrator can call an explicitly configured unattended local
program. It never invokes a shell: `providers.ai.command` is an argument list,
and DRAGON appends `--operation <name>`. Requests are one UTF-8 JSON value on
stdin; responses are one UTF-8 JSON value on stdout. Diagnostic text belongs on
stderr. The process must exit nonzero on failure.

The provider remains unavailable until its command exists and
`integration_test_status` is `PASS`. Run `python dragon_provider_check.py` to
execute the health check while the status is still `NOT_RUN`; record `PASS`
only after reviewing a genuine result. This mechanism does not install a model,
buy API access, or treat an interactive chat session as unattended capability.

## Operations

- `healthcheck` receives `schema_version`. It returns `status: PASS`,
  `unattended: true`, and a provider identity. It must prove the configured
  runtime can start without prompts or GUI interaction.
- `research` receives the edition date, Arabic language, and up to 30 immutable
  prior production continuity snapshots. It returns the same date plus nonempty
  sources. Every source requires a unique ID, exact HTTPS
  page URL (not a homepage), publisher, publication/access timestamps, source
  type, and the claim it supports.
- `articles` receives the verified research packet. It returns exactly one
  decision for every fixed V5 section. A skipped section requires a specific
  reason. An active section requires headline, standfirst, honest byline,
  connected paragraph body, known source IDs, and explicit lead, nut graf,
  verified facts, context, uncertainty, consequences, and next steps.

The adapter enforces configurable hard safeguards of 350 words per active item
and 4,000 words per edition by default. These are rejection thresholds, not
padding targets; the higher editorial ranges in `SPEC-v5.md` remain the quality
standard. Fact-check and Arabic QA still run as separate stages after provider
output is accepted.

After final QA, V5 writes `continuity.json` inside the dated edition before
marking local publication complete. It records covered story identities, exact
source URLs, skipped-section reasons, and declared next steps. Later research
reads only earlier snapshots labelled `production`; synthetic runs can never
seed real editorial continuity. The snapshot is part of the edition manifest
and Git archive, avoiding mutation of V4 memory files.
