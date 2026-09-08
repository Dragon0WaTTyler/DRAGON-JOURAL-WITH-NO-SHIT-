# DRAGON technical specification — Version 5

## 1. Runtime authority

The primary production runtime is the configured local Windows machine. Exactly
one Task Scheduler entry invokes exactly one orchestrator. The orchestrator is
the only component allowed to advance a V5 daily run. GitHub Actions may verify
commits but must not independently start or complete a V5 edition.

The root command is `python dragon_daily.py`. It supports a normal run,
`--resume`, `--retry STAGE`, `--from STAGE`, and `--status`. The command and all
stages use `Africa/Casablanca` unless a future explicitly versioned contract
changes the newspaper timezone.

## 2. Stage graph

The authoritative stage order is:

1. `preflight`
2. `research`
3. `source_intelligence`
4. `article_generation`
5. `chief_editor`
6. `factcheck`
7. `arabic_language_qa`
8. `cover`
9. `publication_source`
10. `pdf`
11. `epub`
12. `final_qa`
13. `github_archive`
14. `whatsapp_delivery`

Every stage declares prerequisites, inputs, outputs, acceptance validation, and
retry policy. A stage record contains status, start/end timestamps, attempt
count, stable error code and detail, artifact hashes, and recovery history.
Allowed stage states are `PENDING`, `RUNNING`, `COMPLETE`, `FAILED`, `BLOCKED`,
and `DEGRADED`.

Successful stage output is a checkpoint. Resume validates its hashes and
acceptance evidence. A failure in EPUB, archive, or delivery must not regenerate
research, articles, editorial work, cover, or a valid PDF.

## 3. State and filesystem

The authoritative state is `daily-runs/YYYY-MM-DD/state.json`. Writes use a
temporary file and atomic replace, retain a previous-good recovery copy, and
must not corrupt the only state on process interruption. Existing V4
`status.json` files are historical inputs. A V5 importer may map them without
overwriting or normalizing them in place.

Transient work and logs remain under the dated run directory. Reader artifacts
remain under `editions/YYYY/MM/YYYY-MM-DD/`. Output hashes bind state to exact
artifacts. A process lock and run identity prevent simultaneous editions and
allow the watchdog to distinguish a live run from an abandoned lock.

State also records a content-derived runtime fingerprint covering the V5
executable code and production-affecting configuration. Run reports repeat that
fingerprint. Cutover evidence is valid only against the current fingerprint;
runtime drift blocks ordinary resume and requires an explicit restart from
`preflight`. Cutover activation switches are deployment state and are excluded
so activating a proven runtime does not invalidate its trial editions.

## 4. Editorial product

DRAGON is a newspaper. Preserve the V4 fixed section inventory and require each
section to be `ACTIVE` or `SKIPPED` with a specific editorial reason. A section
normally has one substantial lead plus verified briefs when useful; a section
without a sufficiently verified story is skipped rather than padded.

Lead articles normally contain a headline, standfirst, configurable byline,
lead, nut graf, verified facts, chronology and context, relevant actors, useful
data, material competing positions, uncertainty, consequences, next steps, and
source references. Recommended ranges remain quality ranges: leads 1000–1500,
standard articles 700–1000, analysis 900–1400, long-form 1500–2200+, and briefs
80–200 words. Never invent prose to hit a range. The front page selects and
presents the strongest stories without duplicating all lead prose. Page count
expands before verified prose is cut.

The visible edition must not repeat a summary-card template across stories.
Research packets may remain structured; reader-facing articles must be connected
journalism. The source policy separates discovery, verification, primary and
independent evidence, facts, claims, unknowns, and disputed points.

## 5. Arabic contract

Reader-facing V5 content uses professional journalistic Arabic in Arabic script.
Do not transliterate the newspaper into Latin script. Technical proper nouns may
retain official spelling where needed. The byline is configured, with a form
such as `تحرير: <PEN_NAME>`, and never implies reporting that did not happen.

HTML/XHTML requires `lang="ar"` and `dir="rtl"`. EPUB package metadata declares
Arabic and right-to-left page progression. PDF rendering must shape Arabic and
handle mixed Arabic/Latin names, punctuation, lists, headlines, and columns.

Language QA is separate from fact-checking. It may improve grammar, clarity,
flow, repetition, leakage, and typography but cannot alter facts. Deterministic
results include `ARABIC_LANGUAGE`, `RTL`, `UTF8`, `ARABIC_RENDERING`, `MOJIBAKE`,
and `FOREIGN_LANGUAGE_LEAKAGE`. Arabic-script presence is not an error.

## 6. Providers and truthful capability

Research, article generation, editing, cover generation, code repair, GitHub,
and WhatsApp integrations are provider interfaces. No paid model API or new paid
service is enabled implicitly. Secrets are loaded from environment variables or
uncommitted local configuration. A capability is `AVAILABLE` only after its
configured implementation passes the relevant integration check.

If no unattended AI backend is supported, preflight reports it and the run
stops truthfully or uses an explicitly configured non-AI fixture for testing.
If code repair is unavailable, the recovery engine creates an incident packet
and records that intervention is required.

## 7. Recovery

Failures are classified as `TRANSIENT`, `DEPENDENCY`, `CONTENT`, `VALIDATION`,
`ENVIRONMENT`, `CODE_DEFECT`, `DELIVERY`, or `UNKNOWN`. Recovery uses bounded
attempts and configurable backoff. Known repairs target only the affected stage
or editorial unit. Exhausted or unsafe failures create a redacted incident
directory containing structured context, traceback, attempts, tests, relevant
paths, source revision, and stage state.

Automatic code repair is attempted only for a classified code defect after
ordinary and known recovery fail. It uses isolation, preserves the source
revision and final artifacts, applies the smallest patch, runs targeted and
regression tests, validates the failed stage, and rolls back a failing patch.

## 8. Publication and external outcomes

Local publication is `COMPLETE` only when editorial work is complete, fact check
passes, Arabic QA passes, the required cover state is satisfied, PDF passes,
EPUB passes, and final QA passes. File existence alone is never sufficient.

Archive and delivery are separate outcomes. GitHub archives only a locally
complete edition, pushes without force, reads back exact identities, and records
an archive receipt. WhatsApp sends only through an explicitly configured
provider and records its own receipt. Either may fail and retry independently
while local publication remains `COMPLETE`.

## 9. Scheduling, watchdog, and observability

Task Scheduler configuration is externalized, including start time and target
deadline. Install, remove, test, and run-now helpers manage one scheduled entry.
The watchdog detects a dead orchestrator, stale `RUNNING` stage, or abandoned
lock, captures diagnostics, and invokes `--resume` only when duplicate execution
is excluded.

Every run emits machine-readable state and a concise human report with date,
start, end, duration, publication/PDF/EPUB/cover/archive/WhatsApp outcomes,
recoveries, and unresolved warnings.

## 10. Cutover and acceptance

V5 is built beside V4, then proven with synthetic tests, one manual real edition,
multiple unattended trials, artifact comparison, failure injection, and a full
acceptance audit. External V4 schedules and competing GitHub production polling
are retired only afterward. Useful CI and archive verification remain.

Historical editions are immutable. A completed edition is hash-bound and
returns `ALREADY_PUBLISHED` on an ordinary rerun. Corrections require an explicit
new publication cycle.
