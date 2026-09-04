# Production repair audit — 2026-09-05

Baseline: e97ac7930d6a7a192d5032514ddeeb1d067306af. Scope: the five user-supplied scheduled prompts, repository production contracts, state gates, publication rendering and persistence. Historical journalism was not rewritten or declared verified by this technical audit.

## Confirmed defects and repairs

| Defect | Consequence | Repair |
| --- | --- | --- |
| Saved prompts put cover fourth and publishing fifth; repository reversed them | Conflicting prerequisites and ownership | Unified Cover 4 / Publishing 5, matching the user's active task names |
| Task 3 disclaimed manifest ownership; cover still required it before Task 5 created it | Missing/stale manifest could block cover | Task 3 owns editorial artifacts; Task 4 reads those; Task 5 owns final manifest |
| SVG accepted in supplied prompts but rejected in repo | Image tool failure stopped publication despite a usable cover | SVG_FALLBACK is a supported, visibly labelled canonical cover; generation result stays truthful |
| Generated image shown in ChatGPT but no archived binary | Later renderer cannot retrieve the cover automatically | Require archived exact bytes or use persisted SVG; no expiring image link handoff |
| Five scheduled tasks could finish but renderer was explicitly manual | No fully automatic PDF/EPUB | User-authorized GitHub Actions performs binary-only validation/render/archive, without a model API |
| Renderer set final COMPLETE before GitHub persistence; state tests allowed overall COMPLETE without binaries | False published status | Two-phase archive then SHA-256 fetch verification, followed by final status/memory commit |
| Resume/reset and parallel status writes lacked conflict protection | A late writer could erase another desk's completion | Create-if-absent, conditional SHA writes, bounded reread/merge retry, no blanket same-date reset |
| Cover renderer searched convenient filenames after a bad declared path | Could use wrong or stale cover | Resolve only exact brief path inside dated edition; manifest/status/brief must agree |
| Canonical cover 3:4 forced into A4 with object-fit:cover | Crop/stretch, possible lost masthead/headline | Cover page retains exact 3:4 geometry, contain fitting |
| HTML copied to temporary directory with relative resource base lost | Missing fonts/images/CSS in PDF | Explicit canonical edition base URL; resource fetch restricted to archived edition files |
| EPUB missing required modified metadata; zgh-Latn labelled Darija as Tamazight; print CSS packed into reflowable book | Standards/reader compatibility errors | ary-Latn, UTC dcterms:modified, LTR, reflowable CSS, manifest/spine/link/resource validation |
| Current COMPLETE metadata alone did not bind outputs to inputs | Changed research/edition could retain a stale downstream package | Exact input Git blob lineage across research/editorial/cover/publishing, visible prose equivalence and binary render SHA-256 receipt |
| Future pilot fixtures coexist with dated production files | A naive directory scan could publish future test editions | Automatic selection is limited to Casablanca today and yesterday; explicit future dates rejected |

## Validation

The original 38 tests passed after dependency installation. New regression coverage exercises stale prose, changed research lineage, wrong canonical cover paths, unsafe resources, invalid dates, depth failures, EPUB metadata/links, local-only render semantics, same-day reset prevention, date rollover, failed pushes, exact binary read-back, publication-memory idempotency and a real Linux PDF/EPUB render.

Local Windows execution skips the real WeasyPrint smoke test when native rendering libraries are unavailable. `.github/workflows/test.yml` installs those libraries and sets `DRAGON_RENDER_SMOKE=1`, so CI must run the real renderer before deployment. The initial Linux CI run 33930714770 passed including the real rendering test; later changes require a fresh green run at their exact commit.

Tests use clearly synthetic fixture content and a temporary bare Git remote. A real render test proves executable output, not editorial accuracy or subjective visual quality. The renderer reports `visual_review=NOT_PERFORMED_BY_RENDERER`; it does not invent a human review. Task 4 still requires actual cover visual inspection.

## Operating boundaries

- The five ChatGPT jobs remain the research/writing runtime. GitHub Actions cannot call an inactive or missed ChatGPT scheduled job. Preserve existing schedules; supported additional recovery invocations can improve resilience.
- Source freshness, independence, and factual support still require real research observations; valid JSON and a working URL are insufficient proof. No retrospective fact-check of all archived editions is claimed.
- Changing GitHub source files alone does not edit saved ChatGPT instructions. The five live launchers must point to `prompts/scheduled/` and their save must be verified.
- The binary workflow needs GitHub Actions enabled and contents-write permission on main. It fails on protected-branch/write restrictions and never bypasses them or force-pushes.
- The cron is a recovery poll, not an exact delivery-time guarantee. GitHub may delay scheduled workflows and disable schedules for inactivity. Failure notifications depend on the user's GitHub notification settings.
- No full daily edition may be called successfully published until its exact canonical binary paths and final receipt have been observed after the live run.

## Primary technical references

- [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow): default-branch scheduling and token-trigger behavior informed the push-plus-poll design.
- [EPUB 3.3](https://www.w3.org/TR/epub-33/): package metadata, modification timestamp and core resource media types.
- [WeasyPrint documentation](https://doc.courtbouillon.org/weasyprint/latest/first_steps.html): canonical base URLs and custom resource fetching.
