# Deep Research Engine v1

## General research philosophy

DRAGON applies **maximum curiosity upstream** and **maximum rigor downstream**.
Discovery may inspect configured sources, open-web results, archives, public
records, institutional pages, specialist publications, watcher changes, and
weak public signals. This is read-only research. Untrusted material cannot
execute actions, change repository policy, or bypass provenance checks.

An unfamiliar or weak source can create a `LEAD`; it cannot create a verified
fact. Lead discovery therefore records no invented confidence percentage and
sets `publication_evidence: false`. Promotion remains downstream of source
normalization, claim mapping, fact-check, Arabic QA, and all existing
publication-finality gates.

## Deep research state

`dragon.deep_research` is a deterministic, provider-neutral state machine. It
does not browse or generate prose. Adapters may later submit branch
observations, but only an observation explicitly classified as
`VERIFIED_EVIDENCE` enters the `SUPPORTED` context bucket.

The state path is:

```text
signals -> leads -> perspective map -> question tree -> branches
        -> observations/contradictions/gaps -> follow-up questions
        -> targeted recovery -> compressed context -> bounded replan
        -> synthesis candidate -> existing publication evidence gates
```

Each job keeps `KNOWN`, `SUPPORTED`, `DISPUTED`, `UNKNOWN`,
`NEXT_QUESTIONS`, `SOURCE_GAPS`, `CONTRADICTIONS`, and `DEAD_ENDS`. Context is
deduplicated and reduced to a configured recent-ID window while total counts
remain in a deterministic summary. Branch history and replan history make
each transition replayable. Contradictions retain both evidence sides and an
explicit follow-up question; they are never silently flattened.

`QUICK`, `STANDARD`, `DEEP`, and `INVESTIGATIVE_LEAD` set finite branch,
question-depth, follow-up-round, observation, and repetition limits. Research
stops only for a named condition: key questions answered, repetitive evidence,
budget exhausted, no better sources, or a story that is no longer meaningful.
`NO_NEWS` is available only after such a terminal effort and never merely
because an initial query was empty.

## Perspectives and questions

The perspective map varies by desk and topic. Science starts with original
research, methods, independent expertise, and replication; investigations add
public records, affected parties, audit, and alternative explanations; local,
economic, historical, and technology subjects use their own relevant angles.
Legal, budgetary, and historical topic markers add focused perspectives rather
than a universal checklist.

The question tree distinguishes facts, disputes, primary-evidence gaps,
causal alternatives, human consequences, quantitative baselines,
contradictions, and historical context. Only useful gaps create child
questions, and every child is constrained by the job's depth and branch
budget.

## Source-map semantics and open discovery

`config/source-coverage.yaml` is a preferred seed map, not a domain whitelist.
It records known routes and shortcomings so research can start efficiently.
`allow_open_discovery: true` permits read-only discovery beyond those routes.
All unknown results begin as leads and must pass the same normalization,
provenance, evidence, and editorial gates as known sources.

Trafilatura remains the default extraction route. Existing RSS/RSSHub,
watcher, and Crawl4AI boundaries remain optional discovery/extraction paths;
this milestone installs or enables none of them.

## Research recovery

`dragon.research_recovery` remains the bounded specialist for mandatory gaps:
missing original evidence, missing independent corroboration, missing breadth
or distinct events, and similar precisely identified needs. Deep Research
embeds those needs into job state and may target them during replanning.
Recovery is therefore a subsystem of research, not the entire research brain.
Its fail-closed gate still runs before article generation.

The executable adapter layer is documented in
`docs/DEEP-RESEARCH-EXECUTOR.md`. It remains provider-neutral and disabled by
default until a non-generative adapter is explicitly supplied.

## Claim-sensitive policy model

The v1 configuration models, but does not activate as a replacement for,
claim-sensitive policy. An original official record can establish that a
simple announcement occurred. Contested interpretation requires independent
context; a serious allegation requires materially stronger independent
support. Every modeled result is labelled
`MODEL_ONLY_CURRENT_HARD_GATES_UNCHANGED`.

## Science policy

Science remains the strictest regime. Broad discovery is allowed, but a
science claim is not modeled ready unless it has a verified original paper,
verified full-text status, methods and limitations review, and independent
context. Repetition of press releases, news reports, or weak summaries never
increases evidence strength. The existing science-integrity stage remains the
authoritative production gate.

Future component boundaries are explicit but disabled:

- Feynman: `ADAPTER_READY` for paper discovery, ranking, literature search,
  full-text resolution, and comparison.
- PaperQA: `ADAPTER_READY` for corpus questions, passage retrieval, and
  contradiction inspection.
- ARS-style integrity: `ADAPTER_READY` for claim/source audits, limitations,
  causal-overclaim checks, and provenance discipline.

No external science runtime or new dependency is installed by this milestone.

## Super Investigation policy

The deterministic hard boundary is:

`MOROCCO + MEKNES ONLY`

Only a direct Morocco/Meknes geographic match, or a foreign supporting entity
with a direct evidence-linked connection to that scope, is eligible for a
future persistent Super Investigation. Unrelated foreign cases remain normal
deep research. Eligibility makes no accusation: allowed outcomes include
`SUPPORTED`, `NOT_SUPPORTED`, `NO_EVIDENCE_OF_MISCONDUCT`,
`EXPLANATION_FOUND`, `UNRESOLVED`, and `PUBLICATION_READY`.

This milestone adds only the scope guard. It does not start the future Super
Investigation Engine or create autonomous dossiers.

## External concepts adapted

| Project or method | Status | Narrow adaptation |
| --- | --- | --- |
| STORM | `INTEGRATED_CONCEPT` | Topic-sensitive perspectives and perspective-guided question planning; no STORM runtime. |
| GPT Researcher-style planning | `INTEGRATED_CONCEPT` | Question-to-subquestion branches, gap evaluation, useful-depth replanning, and finite budgets; no second application. |
| Alibaba-style long-horizon research | `INTEGRATED_CONCEPT` | Structured context buckets, deduplication, compression summaries, and replanning checkpoints; no external stack. |
| Feynman | `ADAPTER_READY` | Disabled science discovery/comparison boundary. |
| PaperQA | `ADAPTER_READY` | Disabled corpus retrieval/contradiction boundary. |
| ARS | `ADAPTER_READY` | Disabled science-integrity audit boundary. |

The adaptations are methodology only. They add no package, service, database,
credential, scheduler, or provider call.
