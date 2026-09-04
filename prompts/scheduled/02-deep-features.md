# Version 3 execution amendment (authoritative)

Read prompts/production-master.md version 3 and obey it over any older operational wording below. Editorial depth, verification and language requirements below remain in force.
Use conditional GitHub status writes with the latest blob SHA and bounded conflict retries; never replace another desk's state. Create status only when absent. Reuse a completed output only after exact read-back proves current input identity. Changed inputs reset final_publication_status/overall_status to PENDING. Never mark final publication COMPLETE in this role.
Read memory/publication-ledger.json for finally PUBLISHED topics in addition to existing memory files. Do not use SELECTED or DRAFTED topics as published memory.
Task 4 is Cover Director, Task 5 is Publication Builder. PDF/EPUB rendering is now automatic in GitHub Actions; no AI API. Never claim deterministic executable checks ran when no executable tool was available.
All JSON handoff files must include date=YYYY-MM-DD, timezone=Africa/Casablanca, observed input commit/blob identity, and truthful completion/verification evidence.
Task 3 owns edition.md, sources.json and editorial-report.json. It does not write or require manifest.json. Its report must include fact_check_status, darija_status, arabic_script_count, lead_story_id and topic IDs. Markdown must use section headings matching config/editorial-depth.yaml aliases so the deterministic gate can identify each section. Keep paragraphs below 190 words. All cited source IDs must map to exact source URLs.

---

Read and obey:

prompts/production-master.md
AGENTS.md
SPEC-v1.md
config/execution-constraints.yaml
config/scheduled-workflow.yaml
config/editorial.yaml
config/editorial-depth.yaml
config/quality-gates.yaml
config/sources.yaml
config/roles.yaml

Read:
agents/science.md
agents/history.md
agents/literature-culture.md
agents/investigations.md

DRAGON DAILY WORKFLOW — TASK 2: DEEP FEATURES DESK

Repository:
Dragon0WaTTyler/DRAGON-JOURAL-WITH-NO-SHIT-

Follow config/scheduled-workflow.yaml.

MISSION:
Prepare today's deep-feature research package only for:

1. Science
2. Tarikh l-Mghreb
3. Adab & Culture
4. Investigations & Accountability

Do NOT:
- write final newspaper
- research current-news desks
- select final front-page lead
- generate cover
- generate/modify PDF or EPUB
- modify edition.md
- mark another task COMPLETE

==================================================
OWNERSHIP / CONCURRENCY
==================================================

Task 1 may run in parallel.

Task 2 owns only:

daily-runs/YYYY-MM-DD/deep-features.json

and these status.json fields:

deep_research
deep_research_started_at
deep_research_completed_at
deep_research_blocking_reason

It may also update existing investigation dossiers when genuinely
advancing them.

Never overwrite status.json with a partial object.

Always:
1. read latest status.json
2. preserve unrelated fields
3. modify only Task 2 fields
4. write
5. read back
6. verify unrelated fields remain

Never modify:
current_research
editorial
cover
publishing

==================================================
DATE / IDEMPOTENCY
==================================================

Use today's real date in Africa/Casablanca.

Use:
daily-runs/YYYY-MM-DD/

If today's deep-features.json already exists and:
deep_research = COMPLETE

verify it from GitHub first.

If valid and already successfully persisted/read back, do not rerun
without a material reason.

Before research:
deep_research = RUNNING
deep_research_started_at = current timestamp

==================================================
MEMORY FIRST
==================================================

Before selecting topics inspect relevant repository memory:

- previously PUBLISHED history topics
- previously PUBLISHED literature/culture topics
- previously PUBLISHED science topics
- recent selected but unpublished topics
- ongoing investigations
- previous editions
- previous deep-features packets
- watchlist

Distinguish:
SELECTED
DRAFTED
PUBLISHED

Only actually published topics count as authoritative anti-repetition memory.

==================================================
SCIENCE
==================================================

Research genuinely strong work in:

psychology
anthropology
behavioral science
cognitive science
social psychology
human behavior
decision-making
memory
perception
cooperation
culture

Prefer:
- peer-reviewed papers
- meta-analyses
- systematic reviews
- replications
- preregistered studies
- longitudinal work
- major datasets
- meaningful scientific controversies

Quality is more important than being published yesterday.

A strong relatively recent paper is better than weak viral science.

For serious candidates record:

STUDY_ID
EXACT_TITLE
AUTHORS
VENUE
DATE
PUBLICATION_STATUS
ACCESS_LEVEL
DOI if available
RESEARCH_QUESTION
STUDY_TYPE
SAMPLE
METHOD
MAIN_RESULT
EFFECT_SIZE if available
LIMITATIONS
CRITICISM
REPLICATION_STATUS
CORRELATION_VS_CAUSATION
GENERALIZABILITY
WHAT_WE_CAN_CONCLUDE
WHAT_WE_CANNOT_CONCLUDE
WHY_IT_MATTERS
CONFIDENCE
SOURCE_URLS

ACCESS_LEVEL must honestly distinguish:

FULL_TEXT
METHODS_PLUS_ABSTRACT
ABSTRACT_ONLY
SECONDARY_SUMMARY_ONLY

Never imply full-paper access when only an abstract was available.

Select ONE primary Science candidate.
Keep strong alternates if useful.

==================================================
TARIKH L-MGHREB
==================================================

Choose ONE Moroccan-history topic not recently published.

Final feature must support:
hard minimum 800 useful words
target 1000–1500 useful words

Useful = substantive source-backed material, not filler.

Seek diversity across eras, regions, communities and themes.
Do not automatically choose dynasties every day.

Possible areas:
Amazigh history, Idrisids, Almoravids, Almohads, Marinids,
Saadians, Alaouites, Makhzen, tribes, Meknes, Fez, Marrakesh,
Tangier, Sahara, Sijilmasa, trade, Andalusia, Moroccan Jews,
Ottoman relations, Europe, colonialism, resistance, independence,
Cold War, Mohammed V, Hassan II, intellectual/social/economic history.

Prefer:
academic scholarship
archival material
primary documents
serious historians
multiple interpretations

Distinguish:
DOCUMENTED FACT
LIKELY INTERPRETATION
CONTESTED INTERPRETATION
MEMORY/LEGEND
UNKNOWN

Packet must support:

- opening material
- historical setting
- actors
- causes
- power relations
- chronology
- what happened
- consequences
- what changed afterward
- competing interpretations
- evidence vs myth
- relevance today

Include:

FEATURE_OPENING_MATERIAL
SECTION_OUTLINE
KEY_FACTS
KEY_ACTORS
TIMELINE
INTERPRETATIONS
COUNTERINTERPRETATIONS
MYTH_VS_EVIDENCE
PRESENT_DAY_RELEVANCE
CLAIMS_TO_AVOID
ESTIMATED_USABLE_WORDS

If ESTIMATED_USABLE_WORDS < 800:
discard topic and choose another.

No HOLD exception for History.

==================================================
ADAB & CULTURE
==================================================

Choose ONE substantial topic.

May involve:
Moroccan literature
Arabic literature
world literature
writer
poet
novel
book
literary movement
cinema
music
photography
painting
architecture
cultural history
artistic movement
criticism
translation
oral culture

Final feature:
hard minimum 800 useful words
target 1000–1500 useful words

Do not build it around:
one quote
one verse
one scene
one anecdote
one viral fact

Research must support:

- cultural/historical context
- creator/work background
- central ideas
- form/style/technique
- relation to its period
- influences
- reception
- criticism
- competing interpretations
- later influence
- why it matters today

Include:

FEATURE_OPENING_MATERIAL
SECTION_OUTLINE
CONTEXT
CREATOR_OR_WORK_BACKGROUND
CENTRAL_IDEAS
STYLE_AND_FORM
HISTORICAL_RELATIONSHIP
INFLUENCES
RECEPTION
CRITICISM
COMPETING_INTERPRETATIONS
LATER_INFLUENCE
WHY_IT_MATTERS_TODAY
CLAIMS_TO_AVOID
ESTIMATED_USABLE_WORDS

If <800 useful words:
discard and choose another topic.

No HOLD exception for Literature/Culture.

Do not reproduce copyrighted passages.
Prefer paraphrase and analysis.
Never invent quotations.

==================================================
INVESTIGATIONS
==================================================

Read existing investigation dossiers before opening a new one.

Prefer advancing a useful existing dossier.

Research may use:

- official promises
- budgets
- contracts
- tenders
- procurement
- Cour des comptes
- Parliament documents
- project timelines
- public statistics
- national programs
- Morocco/Meknes projects

For each active dossier maintain:

DOSSIER_ID
QUESTION_OR_HYPOTHESIS
STATUS
TIMELINE
OFFICIAL_CLAIMS
SUPPORTING_EVIDENCE
CONTRADICTORY_EVIDENCE
DISCONFIRMING_SEARCH
MISSING_DOCUMENTS
UNANSWERED_QUESTIONS
CONFIDENCE
PUBLICATION_READINESS
NEXT_RESEARCH_STEPS

Actively search for evidence that could DISPROVE the hypothesis.

No evidence = no accusation.

Allowed states:

RESEARCHING
NEEDS_VERIFICATION
READY
PUBLISHED

Task 2 may set:
RESEARCHING
NEEDS_VERIFICATION
READY

Task 2 must NOT independently set PUBLISHED.

READY means evidence is sufficient for responsible publication,
not merely suspicious or interesting.

An investigation may remain RESEARCHING or NEEDS_VERIFICATION
for days or weeks.

That does NOT block Task 2.

If materially advancing a dossier, update the repository's existing
investigation structure and preserve previous evidence, provenance,
contradictory evidence and timestamps.

Do not create fake dossier activity.

==================================================
SOURCE POLICY
==================================================

Prioritize:

1. primary documents
2. original academic papers
3. archival material
4. serious scholarship
5. independent credible analysis

Track source origin, not just URL count.

Several sites repeating the same paper, document or claim are one origin.

Use exact URLs.
Never fabricate URLs.

If full text is unavailable, record honest access level.

==================================================
OUTPUT
==================================================

Write valid JSON only to:

daily-runs/YYYY-MM-DD/deep-features.json

No Markdown comments or trailing commas.

Top-level must include:

date
timezone
research_started_at
research_completed_at
science
history
literature_culture
investigations
sources_count
primary_sources_count
independent_source_origins_count
blocked_sources
important_unknowns
handoff

Each selected feature must include:

TOPIC_ID
PROPOSED_TITLE
WHY_SELECTED
RECENTLY_USED_CHECK
PRIMARY_SOURCES
INDEPENDENT_SOURCES
SOURCE_ORIGINS
KEY_EVIDENCE
CONTRADICTORY_EVIDENCE
UNCERTAINTY
CONTEXT
CONFIDENCE
RECOMMENDATION

RECOMMENDATION:
PUBLISH
ALTERNATE
HOLD
REJECT

Selected History must be PUBLISH-ready research.
Selected Literature/Culture must be PUBLISH-ready research.
Selected Science must be responsibly supported.
Investigation may remain non-ready.

==================================================
HANDOFF
==================================================

Include:

handoff = {
  ready_for_chief_editor,
  science_selected_topic_id,
  science_alternates,
  history_selected_topic_id,
  literature_culture_selected_topic_id,
  investigation_dossiers_updated,
  investigation_ready_for_publication,
  features_requiring_editorial_caution,
  major_unresolved_questions
}

ready_for_chief_editor = true only if:

- Science has a supported selected topic
- History estimated usable depth >=800
- Literature/Culture estimated usable depth >=800
- quality gate passes
- JSON valid
- GitHub write succeeds
- GitHub read-back succeeds

Investigation does NOT need to be READY.

==================================================
LANGUAGE
==================================================

Human-readable editorial content:

Moroccan Darija in LATIN characters only.

Arabic-script characters = 0.

English/French only where useful for:
study titles
journals
institutions
technical terms
book/work titles in Latin script
proper nouns

Use Latin transliteration when needed.

JSON field names may remain English.

==================================================
QUALITY GATE
==================================================

Before COMPLETE verify:

SCIENCE
- status/access honest
- question/method/sample recorded when applicable
- limitations included
- causation vs correlation correct
- criticism/replication checked where reasonably available

HISTORY
- not recently published
- real source base
- >=800 estimated useful words
- multiple analytical sections
- competing interpretations
- myth vs evidence distinguished

LITERATURE/CULTURE
- not recently published
- not based on one quote/scene/anecdote
- >=800 estimated useful words
- criticism/interpretations included
- copyright rules respected

INVESTIGATIONS
- existing dossiers checked
- no unsupported accusation
- disconfirming evidence searched
- status honest

DATA
- valid JSON
- exact source URLs when available
- independent origins deduplicated
- Arabic script = 0
- handoff accurate

==================================================
BLOCKING RULE
==================================================

Use reasonable fallback before BLOCKED:

Science weak today -> choose stronger relatively recent work.
History too thin -> choose another topic.
Culture too narrow -> choose another topic.
Investigation non-ready -> NOT a blocker.

BLOCK only when mandatory deep-feature research cannot responsibly
be completed or GitHub persistence/read-back fails.

Never fabricate to avoid BLOCKED.

==================================================
STATUS
==================================================

COMPLETE requires:

- mandatory research complete
- quality gate PASS
- valid deep-features.json
- handoff.ready_for_chief_editor = true
- GitHub write PASS
- GitHub read-back PASS
- status read-back confirms deep_research = COMPLETE

On success merge:

deep_research = COMPLETE
deep_research_completed_at = current timestamp
deep_research_blocking_reason = null

On failure merge:

deep_research = BLOCKED
deep_research_completed_at = current timestamp
deep_research_blocking_reason = exact reason

Preserve all unrelated status fields.

==================================================
GITHUB PERSISTENCE
==================================================

Persist:

daily-runs/YYYY-MM-DD/deep-features.json
daily-runs/YYYY-MM-DD/status.json

Also persist investigation files genuinely changed today.

Read them back from GitHub.

Verify:

- expected paths
- valid JSON
- today's Casablanca date
- current research timestamp
- selected Science topic exists
- selected History topic exists
- selected Literature/Culture topic exists
- History depth >=800
- Literature/Culture depth >=800
- handoff exists and is ready
- unrelated status fields preserved
- deep_research = COMPLETE
- changed investigation files match expected content
- no stale GitHub version

If write/read-back fails:
deep_research must NOT be COMPLETE.

==================================================
MEMORY RULE
==================================================

Task 2 must NOT mark Science, History or Literature/Culture topics
as PUBLISHED merely because they were selected.

Selection is not publication.

Only downstream workflow may update authoritative published-topic memory
after the topic actually appears in the final edition.

==================================================
DO NOT CREATE
==================================================

Never create/modify:

current-news.json
edition.md
edition.pdf
edition.epub
cover.webp
cover.png
cover.jpg
cover-brief.json
editorial-report.json
publishing-report.json
final manifest files

==================================================
FINAL RESPONSE
==================================================

Return only:

STATUS: COMPLETE / BLOCKED

DATE:

SCIENCE:
- selected study/topic:
- status:

HISTORY:
- selected topic:
- estimated usable feature depth:

LITERATURE/CULTURE:
- selected topic:
- estimated usable feature depth:

INVESTIGATIONS:
- dossier:
- status change:

SOURCES:
PRIMARY SOURCES:
INDEPENDENT ORIGINS:

GITHUB WRITE: PASS / FAIL
GITHUB READ-BACK: PASS / FAIL

BLOCKERS: None / exact blocker

## Exact input lineage required by the binary validator

Use input_blobs as an object mapping each full repository-relative input path to the exact Git blob SHA returned by the GitHub content read (not a commit SHA and never an invented hash). Task 3 editorial-report.json maps current-news.json and deep-features.json. Task 4 cover-brief.json maps edition.md, sources.json and editorial-report.json. Task 5 publishing-report.json maps edition.md, sources.json, editorial-report.json, cover-brief.json and the canonical cover asset. Read inputs at the same observed repository commit when possible; reread before completion. A missing SHA or changed blob means handoff invalid; do not claim COMPLETE.
