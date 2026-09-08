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

The repository includes an opt-in adapter at
`scripts/codex_editorial_provider.py` for the detected Codex CLI. It invokes
`codex exec` ephemerally with web search, a read-only sandbox, no approvals,
and a JSON output schema. The command-level health check only proves that the
CLI and ChatGPT login exist; it deliberately reports
`editorial_generation_tested: false`. Do not change
`integration_test_status` from `NOT_RUN` to `PASS` until both a live research
packet and article response pass the V5 adapter validators and human review.
The adapter consumes the signed-in account's Codex usage and is never enabled
as a paid API or silently assigned an API key. `DRAGON_CODEX_BINARY` and
`DRAGON_CODEX_MODEL` are optional local overrides.

`python dragon_provider_check.py` is a no-generation CLI/auth probe. A deliberate
`python dragon_provider_check.py --full --date YYYY-MM-DD` consumes the signed-in
account's Codex usage, runs both live operations, validates them through the
same production adapter, and writes hash-addressed review material beneath
`acceptance/provider-trials/YYYY-MM-DD/`. Even a technically valid trial is
labelled `VALIDATED_AWAITING_HUMAN_REVIEW` and never edits configuration or
promotes itself to `PASS`.

During a full trial the adapter also atomically captures each structured model
response as `research.raw.json` or `articles.raw.json` before the production
validator runs. If validation fails, the command reports those paths so the
failure can be diagnosed without another blind model call. Raw output never
counts as accepted evidence; only normalized artifacts from a fully validated
trial enter `receipt.json`. Inventory errors report the exact missing, unknown,
duplicate, and structurally invalid section identifiers. The Structured Output
schemas constrain both research and article arrays to exactly the 23 fixed
section decisions, while the validator independently enforces identity and
uniqueness.

Cutover does not trust the configuration flag alone. The trial receipt binds
the current V5 runtime fingerprint, Git revision, creation time, and SHA-256 of
the exact research/article artifacts. After inspecting those artifacts, a
human editor creates `review.json` in the same trial directory using this
shape (with real identity, timestamp, receipt hash, and judgments):

```json
{
  "schema_version": 5,
  "status": "PASS",
  "reviewed_by": "<human editor>",
  "reviewed_at": "2026-09-08T12:00:00+01:00",
  "receipt_sha256": "<sha256 of receipt.json>",
  "checks": {
    "sources": "PASS",
    "factual_accuracy": "PASS",
    "arabic_quality": "PASS",
    "article_depth": "PASS",
    "section_decisions": "PASS"
  }
}
```

The review timestamp must be timezone-aware and no earlier than the trial.
Acceptance recomputes every hash and requires the trial runtime to equal the
current runtime. Altered artifacts, a stale adapter/runtime, missing review, or
any non-`PASS` judgment keeps `editorial_provider_proven` false even if someone
manually changes `integration_test_status` to `PASS`.

## Operations

- `healthcheck` receives `schema_version`. It returns `status: PASS`,
  `unattended: true`, and a provider identity. It must prove the configured
  runtime can start without prompts or GUI interaction.
- `research` receives the edition date, Arabic language, and up to 30 immutable
  prior production continuity snapshots. It returns the same date, nonempty
  sources, and exactly one decision for every fixed section. Each decision has
  at least two uniquely identified ranked candidates, identifies the selected
  candidate with a reason, and records discovery, verification, primary, and
  independent evidence IDs plus facts, claims, unknowns, and disputed points.
  Every source requires a unique ID, exact HTTPS
  page URL (not a homepage), publisher, publication/access timestamps, source
  type, and the claim it supports.
- `articles` receives the verified research packet. It returns exactly one
  decision for every fixed V5 section. A skipped section requires a specific
  reason. An active section requires headline, standfirst, honest byline,
  connected paragraph body, known source IDs, the selected research candidate,
  a continuity story key, structured claim records, and explicit lead, nut graf,
  verified facts, context, uncertainty, consequences, and next steps. Material
  facts must survive claim-level primary and independent evidence checks.

The adapter enforces configurable hard safeguards of 350 words per active item
and 4,000 words per edition by default. These are rejection thresholds, not
padding targets; the higher editorial ranges in `SPEC-v5.md` remain the quality
standard. A deterministic chief-editor gate ranks active stories for the front
page and rejects duplicate story identities/headlines or contradictory keyed
facts. Claim-level fact-check and Arabic QA still run as separate stages after
provider output is accepted.

After final QA, V5 writes `continuity.json` inside the dated edition before
marking local publication complete. It records covered story identities, exact
source URLs, skipped-section reasons, and declared next steps. Later research
reads only earlier snapshots labelled `production`; synthetic runs can never
seed real editorial continuity. The snapshot is part of the edition manifest
and Git archive, avoiding mutation of V4 memory files.

Continuity ingestion is fail-closed: the next run also requires the prior daily
state to say publication and `final_qa` are `COMPLETE`, requires the final-QA
report itself to be hash-valid against that checkpoint, and requires that
report to contain the exact current `continuity.json` hash. A loose, failed, or
subsequently modified snapshot is ignored.
