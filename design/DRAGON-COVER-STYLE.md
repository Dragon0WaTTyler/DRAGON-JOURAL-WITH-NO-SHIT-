# DRAGON Cover Style Contract

## Version 4 newspaper cover system

The cover is a newspaper front system, not a standalone infographic. Keep one
dominant editorial visual, but organise it in five readable layers:

1. DRAGON masthead.
2. ISO date and edition line.
3. One dominant visual concept tied to the final lead.
4. One short lead headline with clear contrast.
5. A bottom teaser rail carrying zero to two secondary verified stories.

Use the black/white/red system with deliberate empty space. The visual may be
symbolic, portrait-led or illustrated; it must not impersonate a documentary
photograph. Teasers are headlines only, never dense summaries. The Cover
Director records `layout_system: EDITORIAL_MASTHEAD_LEAD_RAIL`, the exact
headline/teasers and hierarchy QA in cover-brief.json. A v4 SVG fallback uses
the same masthead/date/lead/rail order and does not reduce the cover to a data
card.

Permanent art direction for DRAGON covers. Use one strong editorial idea, not a collage.

## Tested workflow

The permanent Scheduled Work flow is intentionally compact because end-to-end testing found that a large all-in-one prompt failed image generation, while a minimal capability test and a compact persisted cover brief both passed.

1. require editorial `COMPLETE`
2. do not require the downstream publication-source package or manifest
3. read the final edition and editorial report
4. read this style contract
5. select exactly one lead
6. select exactly one cover mode
7. create compact `daily-runs/YYYY-MM-DD/cover-brief.json`
8. persist the brief to GitHub and read it back
9. generate one actual portrait cover close to 3:4
10. run visual QA
11. if generation fails, retry once only with an even simpler composition
12. update the brief and workflow status

Never expand a failed prompt into a more complex multi-stage image request.

## Visual system

Use one dominant concept and a black/white/red hierarchy. Optional restrained neutral backgrounds are acceptable. The main visual should dominate attention.

Visible text should be minimal:
- DRAGON masthead
- date
- one main headline
- a bottom rail with maximum two secondary teasers

All ordinary cover text is Moroccan Darija in Latin characters. Arabic script is prohibited.

## Cover modes

Choose one:
- portrait dossier
- symbolic editorial
- satirical caricature
- dramatic current-event editorial

Generated art must remain identifiable as editorial illustration. Never fabricate documentary evidence or imply that a generated scene is a real news photograph.

## Composition rules

Prefer a clear hierarchy readable on a phone thumbnail. Do not use unrelated collage, excessive labels, dense article copy, or multiple competing visual metaphors.

The cover should be portrait, approximately 3:4. One concept, one lead, one mode.

## Archive semantics

Task 4 is COMPLETE only after the canonical cover is persisted and visually verified.
Use AI_GENERATED only with actual archived bytes. If generation or binary archival is unavailable, use a self-contained, visually verified SVG_FALLBACK. It is a valid cover but never image_generation_status PASS. Preserve its exact 3:4 aspect ratio. Always include the ISO date. No external resources, scripting, use/image elements or foreignObject in the SVG.
