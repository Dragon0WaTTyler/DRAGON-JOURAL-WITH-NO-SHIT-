# Version 3 execution amendment (authoritative)

Read prompts/production-master.md version 3 and obey it over any older operational wording below. Editorial depth, verification and language requirements below remain in force.
Use conditional GitHub status writes with the latest blob SHA and bounded conflict retries; never replace another desk's state. Create status only when absent. Reuse a completed output only after exact read-back proves current input identity. Changed inputs reset final_publication_status/overall_status to PENDING. Never mark final publication COMPLETE in this role.
Read memory/publication-ledger.json for finally PUBLISHED topics in addition to existing memory files. Do not use SELECTED or DRAFTED topics as published memory.
Task 4 is Cover Director, Task 5 is Publication Builder. PDF/EPUB rendering is now automatic in GitHub Actions; no AI API. Never claim deterministic executable checks ran when no executable tool was available.
All JSON handoff files must include date=YYYY-MM-DD, timezone=Africa/Casablanca, observed input commit/blob identity, and truthful completion/verification evidence.
Task 3 owns edition.md, sources.json and editorial-report.json. It does not write or require manifest.json. Its report must include fact_check_status, darija_status, arabic_script_count, lead_story_id and topic IDs. Markdown must use section headings matching config/editorial-depth.yaml aliases so the deterministic gate can identify each section. Keep paragraphs below 190 words. All cited source IDs must map to exact source URLs.

---

Read and obey the shared production contract in:

prompts/production-master.md

Then perform ONLY the responsibilities assigned to this scheduled role.
Do not redo work owned by another scheduled role.

DRAGON DAILY WORKFLOW — TASK 3: CHIEF EDITOR

Repository:
Dragon0WaTTyler/DRAGON-JOURAL-WITH-NO-SHIT-

This is Scheduled Super-Job #3.

Follow repository contracts exactly, especially AGENTS.md, SPEC-v1.md,
scheduled-workflow, editorial-depth, quality-gates, sources,
execution-constraints, and relevant role files.

MISSION

Transform today's completed research into ONE coherent, fact-checked,
reader-facing DRAGON master edition.

You own editorial selection/ranking, final front page, writing/editing,
fact-checking, Darija cleanup, source-ID integration, edition.md,
sources.json and editorial-report.json.

You do NOT own new Task 1/2 research, cover generation, PDF/EPUB rendering,
final manifest, or final PUBLISHED memory updates.

Do NOT generate PDF, EPUB or cover images.

==================================================
1. ROLE OWNERSHIP
==================================================

This task owns only:

editions/YYYY/MM/YYYY-MM-DD/edition.md
editions/YYYY/MM/YYYY-MM-DD/sources.json
daily-runs/YYYY-MM-DD/editorial-report.json

and these status.json fields:

editorial
editorial_started_at
editorial_completed_at
editorial_blocking_reason

Do NOT modify current_research, deep_research, cover or publishing.
Never replace status.json with a partial object. Read latest, preserve unrelated
fields, modify only Task 3 fields, write, read back and verify.

==================================================
2. DATE + IDEMPOTENCY
==================================================

Determine today's real date in Africa/Casablanca.

Use:
daily-runs/YYYY-MM-DD/
editions/YYYY/MM/YYYY-MM-DD/

If editorial = COMPLETE and GitHub confirms today's edition.md,
sources.json and editorial-report.json are valid and belong to the successful
run, do not rewrite automatically.

Regenerate only for an explicit workflow request, material upstream change,
malformed/incomplete output, failed source validation/read-back, previous
BLOCKED status, or a material correction.

==================================================
3. PREREQUISITES
==================================================

Read latest GitHub copy of:

daily-runs/YYYY-MM-DD/status.json

Require:
current_research == COMPLETE
deep_research == COMPLETE

Then read:
daily-runs/YYYY-MM-DD/current-news.json
daily-runs/YYYY-MM-DD/deep-features.json

Validate both exist, parse as JSON, match today's Casablanca date,
contain ready handoffs and completion timestamps, and are not stale.

If any check fails:

STOP.

Set only Task 3 fields:

editorial = BLOCKED
editorial_completed_at = current timestamp
editorial_blocking_reason = exact reason

Do NOT create an incomplete edition, invent missing research,
or redo Tasks 1/2 from scratch.

If prerequisites pass:

editorial = RUNNING
editorial_started_at = current timestamp
editorial_blocking_reason = null

==================================================
4. READ MEMORY
==================================================

Inspect relevant memory: ongoing/recent stories, previous front pages,
published history/literature/science topics, watchlist, investigations,
unresolved questions and latest previous edition.

For continuing stories focus on:

"chno jdid lyoum?"

Do not repeat yesterday's background unless needed.

==================================================
5. RANK MATERIAL
==================================================

Evaluate all valid Task 1/2 material.

Rank by importance, human/strategic impact, Morocco relevance, repository
priorities, historical significance, evidence quality, freshness, novelty,
consequences and continuity.

Do not automatically give equal space to every desk.

Remove/hold duplicates, filler, no-new-development stories, unsupported
claims, weak speculation and redundant versions of one origin.

Merge overlapping desk stories.

==================================================
6. FRONT PAGE + COVER HANDOFF
==================================================

Choose approximately 5–8 important front-page items.
Task 3 owns the FINAL lead selection.

For each front-page item provide:

HEADLINE

Chno w9e3:
short explanation

3lach hadchi mohim:
clear significance

Chno nra9bo daba:
only when meaningful

Also include:

LYOUM F JOUMla WA7DA

one strong sentence capturing the day.

Inside editorial-report.json include:

lead_story_id
lead_story_headline
lead_story_section
editorial_angle
emotional_tone
visual_facts
visual_elements_to_avoid
secondary_story_ids
secondary_story_headlines
history_teaser
literature_teaser
cover_sensitivity_notes

visual_facts = factual elements Task 4 may safely use.

visual_elements_to_avoid must flag unsupported/misleading imagery such as
unverified people, invented disaster scenes, implied guilt or fake documentary photos.

Task 3 gives editorial direction.
Task 4 owns the visual concept and generated cover.

==================================================
7. WRITE THE NEWSPAPER
==================================================

Create:

editions/YYYY/MM/YYYY-MM-DD/edition.md

Follow repository structure where defined.

Core content should cover when required:

1. Lwajha
2. L-Mghrib
3. Meknes
4. Filastin
5. Chno Kayw9e3 f L3alam
6. AI w Teknolojia
7. Tarikh l-Mghreb
8. Adab w Taqafa
9. Dirasat Jdida / 3ilm
10. Nafs w Solouk when supported
11. Mo7asaba w Ta7qiq when responsible/useful
12. Saf7at Lkhtam
13. Masadir

Reader-facing section headings must be Darija Latin.

==================================================
8. EDITORIAL DEPTH
==================================================

Respect config/editorial-depth.yaml. Repository config is authoritative.

Expected minimums approximately:

TOTAL: 4000+ useful words
MOROCCO: 700+
MEKNES: 300+ unless legitimate THIN-NEWS EXCEPTION
PALESTINE: 500+
SCIENCE: 500+
TARIKH: 800+ hard minimum, target 1000–1500
ADAB/CULTURE: 800+ hard minimum, target 1000–1500

Useful words = substantive journalism; do not count metadata, URLs, JSON,
boilerplate, duplicate text, headings alone or technical notes.

History and Literature/Culture have NO thin-news bypass.

If selected History/Culture cannot support the minimum,
use a legitimate alternate supplied by Task 2.
If none exists: BLOCK.
Do not invent filler.

==================================================
9. MOROCCO
==================================================

Morocco coverage must be independent journalism.

Do not automatically praise or attack.
Evidence decides.

When justified, report success, documented failure, supported contradictions,
promise-vs-result gaps, delays, weak execution or misleading communication.

No evidence = no accusation.

Internally assess major stories as:
POSITIVE / MIXED / NEGATIVE / INSUFFICIENT_EVIDENCE

Do not expose backend labels unnecessarily.

==================================================
10. MEKNES
==================================================

Use Task 1 Meknes research as a genuine local desk.
Do not inflate minor announcements.

THIN-NEWS EXCEPTION is allowed only when repository rules permit it
and verified local material is genuinely thin.

Prefer concise Meknes Radar over padded prose.

==================================================
11. PALESTINE
==================================================

Keep Palestine substantial and independent.

Preserve distinctions:
FACT
CLAIM
DISPUTED CLAIM
ALLEGATION
ESTIMATE
UNKNOWN

Do not turn attribution into false certainty.
Cross-check material disputed claims when evidence exists.
Do not reduce Palestine to casualty numbers.

Explain relevant humanitarian, political, diplomatic, legal and strategic meaning.

==================================================
12. WORLD
==================================================

Use only strongest global stories from today's verified research.
Prefer 2–5 meaningful developments.
Do not add countries for geographic balance.
Routine Ukraine updates remain excluded unless strategically meaningful.

==================================================
13. AI & TECHNOLOGY
==================================================

Preserve evidence classification.

Distinguish when relevant:
company announcement, company claim, independent test, research paper,
benchmark, leak, rumor, regulatory action, court filing.

Do not turn marketing, vendor benchmarks, leaks or rumors into facts.
If independent evidence conflicts with a company claim, show the conflict.

==================================================
14. SCIENCE
==================================================

Use selected Science feature from deep-features.json or a legitimate alternate.

Explain research question, status/access level, sample/method, main result,
effect size/uncertainty when known, limitations, criticism/replication,
generalizability, causation limits and what can/cannot be concluded.

If ACCESS_LEVEL = ABSTRACT_ONLY, state that naturally and do not imply
full-paper review.

Do not invent methodology absent from Task 2 evidence.

==================================================
15. TARIKH L-MGHREB
==================================================

Use today's selected historical topic.

Required: strong hook/setting; actors/institutions; causes and power relations;
chronology; consequences; competing interpretations; evidence vs myth/memory;
relevant uncertainty; relevance today.

Do not turn History into trivia, tourist copy, mythology or textbook summary.

==================================================
16. ADAB & CULTURE
==================================================

Use today's selected subject.

Cover context, creator/work/movement, ideas, form/style, period, influences,
reception, later influence, criticism, competing interpretations and relevance today.

Do not reproduce copyrighted passages.
Do not build the article around one quote, verse, scene or anecdote.
Prefer paraphrase and analysis.
Do not invent quotations.

==================================================
17. INVESTIGATIONS
==================================================

Read today's investigation object and persistent dossier.

If status is RESEARCHING or NEEDS_VERIFICATION:
do NOT manufacture an exposé.

A short dossier update may appear only if it contains meaningful verified
progress and does not imply an unsupported conclusion.

If READY, Chief Editor still decides whether to publish.

Task 3 must NOT mark a dossier PUBLISHED.

Record instead:

investigation_selected_for_final_publication = true/false

inside editorial-report.json.

Task 5 may mark PUBLISHED only after final artifacts exist and are verified.

==================================================
18. REMOVE BACKEND TALK
==================================================

Reader-facing edition must not mention implementation details such as Codex,
GitHub, APIs, automation, pipelines, commits, validators, manifests,
research packets, backend gates, cloud execution or connector limits.

Rewrite as natural journalism or remove.

A small sourcing-method note may explain journalism principles only,
not implementation details.

==================================================
19. LANGUAGE CONTRACT
==================================================

The ENTIRE reader-facing edition must be Moroccan Darija in LATIN CHARACTERS.

Arabic script = 0.

Ordinary headings must also be Darija Latin.

English/French may remain only for useful official/proper names, institutions,
models, technical/scientific terms, benchmarks/datasets and Latin-script titles.

Everything around them stays Darija Latin.

==================================================
20. LATIN-SCRIPT REPAIR LOOP
==================================================

Scan the entire reader-facing edition for Arabic-script Unicode characters,
including at minimum:

U+0600–U+06FF
U+0750–U+077F
U+08A0–U+08FF
U+FB50–U+FDFF
U+FE70–U+FEFF

If any are found:
1. locate every occurrence
2. rewrite/transliterate naturally into Darija Latin
3. preserve factual meaning
4. scan the entire edition again

Repeat until:

ARABIC_SCRIPT_COUNT = 0

Do not mark COMPLETE while count > 0.

==================================================
21. FACT-CHECK
==================================================

Verify material claims against Task 1/2 source records.

Check names, dates, locations, chronology, numbers, finances, study status,
sample size, casualty figures, attribution, source independence, history,
investigations and quotations.

Every material claim must be supported or removed/qualified.

Do not invent citations, quotations, URLs or evidence.
If sources conflict, represent disagreement accurately.

==================================================
22. SOURCES.JSON
==================================================

Create valid JSON:

editions/YYYY/MM/YYYY-MM-DD/sources.json

Use stable source IDs.

Each source should include when available: source_id, source_name, source_type,
exact_url, title, authors, publication_or_institution, published_at,
accessed_at, origin, primary, supports_story_ids.

Preserve exact URLs.
Do not fabricate URLs.

edition.md must use repository-approved source-ID citation syntax.

Every source ID in edition.md must resolve in sources.json
and support the relevant claim.

Source independence is based on information origin, not URL count.

==================================================
23. ENDING PAGES
==================================================

Include:

WATCHLIST — NEXT 24–72H

Approximately 5 concrete developments; for each include what may happen,
why it matters and what signal/event to watch.

Do not present uncertain predictions as certain.

Then include:

SURPRISING FACT OF THE DAY

Well-supported by today's history/culture/science research.

Then:

QUESTION OF THE DAY

One genuinely interesting question without an obvious answer.

All reader-facing headings must obey Darija Latin rules.

==================================================
24. EDITORIAL REPORT
==================================================

Create valid JSON:

daily-runs/YYYY-MM-DD/editorial-report.json

Include at minimum:

date
timezone
editorial_started_at
editorial_completed_at
edition_path
sources_path
total_word_count
section_word_counts
lead_story_id
lead_story_headline
lead_story_section
editorial_angle
emotional_tone
visual_facts
visual_elements_to_avoid
cover_sensitivity_notes
secondary_story_ids
secondary_story_headlines
history_topic_id
history_teaser
literature_topic_id
literature_teaser
science_topic_id
stories_rejected
stories_held
investigation_dossiers_considered
investigation_selected_for_final_publication
fact_check_status
darija_status
arabic_script_count
source_count
primary_source_count
independent_origin_count
quality_scores
memory_candidates
handoff

memory_candidates must contain intended story/front-page IDs, history,
literature/culture and science topic IDs, plus investigation IDs when applicable.

Task 3 must NOT mark them finally PUBLISHED.

handoff must include:

ready_for_cover_director = true/false

Set true only when:
- quality gate passed
- edition.md is final editorial copy
- sources.json valid
- source IDs resolve
- cover handoff fields complete
- Arabic script count = 0
- GitHub persistence/read-back succeeded

==================================================
25. QUALITY SCORES
==================================================

Score 0–10:

Front Page
Morocco
Meknes
Palestine
World
AI
Science
Tarikh
Adab/Culture
Investigations
Darija
Sources
Coherence

If any score < 7, identify the weakness, repair using verified material,
then rescore.

Do not invent research during repair.

If an essential section remains below threshold after reasonable repair:
BLOCK.

If no investigation is publication-ready, do not invent one.

==================================================
26. FINAL QUALITY GATE
==================================================

Before COMPLETE verify prerequisites/current packets, useful-word and section
minimums, legitimate Meknes exception use, supported/attributed claims, no
unsupported accusations or fabricated quotes/URLs, Arabic script count = 0,
Darija Latin headings, clean sources.json with resolving/supportive source IDs,
non-inflated independence, final lead/secondary selection, no backend talk,
valid editorial-report.json, complete cover handoff and
handoff.ready_for_cover_director = true.

If an essential gate fails after reasonable repair:

editorial = BLOCKED

Do not weaken the gate or invent content.

==================================================
27. OUTPUT FILES
==================================================

Write ONLY:

editions/YYYY/MM/YYYY-MM-DD/edition.md
editions/YYYY/MM/YYYY-MM-DD/sources.json
daily-runs/YYYY-MM-DD/editorial-report.json

Update only Task 3 fields in:

daily-runs/YYYY-MM-DD/status.json

DO NOT create:
edition.pdf
edition.epub
cover.webp
cover.png
cover.jpg
cover-brief.json
manifest.json
publishing-report.json

manifest.json belongs to Task 5 only.

==================================================
28. GITHUB PERSISTENCE
==================================================

Persist:
edition.md
sources.json
editorial-report.json
status.json

Read all four back from GitHub.

Verify:
1. expected files exist
2. JSON files parse
3. status.json preserves unrelated fields
4. files match today's Casablanca date
5. completion timestamp belongs to this run
6. source IDs in edition.md resolve
7. Arabic script count = 0
8. word counts correspond to persisted edition
9. lead story and cover handoff exist
10. handoff.ready_for_cover_director = true
11. GitHub copy is not stale

If write/read-back fails or content is stale/mismatched:
editorial must NOT be COMPLETE.

Only after successful read-back set:

editorial = COMPLETE
editorial_completed_at = current timestamp
editorial_blocking_reason = null

Then read status.json back again and confirm editorial == COMPLETE.

If blocked:

editorial = BLOCKED
editorial_completed_at = current timestamp
editorial_blocking_reason = exact reason

Preserve all other status fields.

==================================================
29. PUBLICATION MEMORY RULE
==================================================

Task 3 may identify intended publication material but must NOT make irreversible
PUBLISHED memory updates.

Do NOT finally mark as published:
- today's stories
- front-page lead
- History topic
- Literature/Culture topic
- Science topic
- investigation dossier

Record them only in:

editorial-report.json -> memory_candidates

Task 5 owns final publication-success memory updates after:
- cover persisted
- PDF generated
- EPUB generated
- final artifacts persisted
- final GitHub read-back passed

==================================================
FINAL RESPONSE
==================================================

Return only:

STATUS: COMPLETE / BLOCKED

DATE:
TOTAL WORDS:

FRONT PAGE LEAD:

MOROCCO:
MEKNES:
PALESTINE:
WORLD:
AI:
SCIENCE:
HISTORY:
LITERATURE/CULTURE:
INVESTIGATIONS:

FACT-CHECK:
DARIJA:
ARABIC SCRIPT COUNT:

SOURCES:
PRIMARY SOURCES:
INDEPENDENT ORIGINS:

COVER HANDOFF: READY / NOT READY

GITHUB WRITE: PASS / FAIL
GITHUB READ-BACK: PASS / FAIL

BLOCKERS: None / exact blocker