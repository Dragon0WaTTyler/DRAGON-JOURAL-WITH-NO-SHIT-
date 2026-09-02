# Daily Newspaper — Technical Specification v1

## Scope

One cloud-run pipeline produces one archived edition. The first run is a
synthetic smoke test. Production research and publication are out of scope
until the cloud, network, persistence, and offline-PC tests pass.

## Editorial roles

The project defines 13 roles, not 13 required persistent processes:

1. Chief Editor / Orchestrator
2. Morocco Desk
3. Meknes Intelligence
4. Palestine & Middle East
5. World Geopolitics
6. AI & Technology
7. Science Research
8. Moroccan History
9. Literature & Culture
10. Investigations & Accountability
11. Fact-check
12. Darija Language Editor
13. Creative Director & Publishing

Research roles may run in parallel when the cloud surface supports it. Fact
checking, language QA, artifact generation, validation, commit, and push are
quality-gated sequential stages.

## Model intent

- Chief Editor, investigations, synthesis, difficult science/history/culture:
  `gpt-5.6` (flagship alias/configuration).
- Discovery and high-volume workers: `gpt-5.6-terra` or `gpt-5.6-luna`.
- The smoke test uses the model configured by the cloud task and does not
  assume that a particular model is available on every account.

## Persistent state

GitHub is the source of truth. Durable state belongs in `memory/`,
`investigations/`, and `editions/`; container state and temporary attachments
are never authoritative.

## Publication gates

1. Research inputs available.
2. Major claims verified.
3. Unsupported accusations removed or held.
4. Long-form sections meet their requested depth.
5. Darija Latin QA passes; Arabic script is rejected for the production rule.
6. Sources support the published claims.
7. PDF and EPUB validate.
8. Archive contract passes and `git commit` + `git push` succeed.

## Cloud-only acceptance test

The test passes only if a cloud run, with the desktop app and PC later
offline, leaves the complete edition and commit visible on GitHub. A local
run, a successful attachment, or an unpushed commit is not success.
