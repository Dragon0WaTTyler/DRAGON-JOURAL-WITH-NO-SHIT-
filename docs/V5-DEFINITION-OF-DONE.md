# DRAGON V5 Definition-of-Done traceability

This register maps all 67 requirements in section 121 of the V5 master
specification to current evidence. It is an implementation and acceptance
ledger, not a declaration that migration or cutover is complete.

Status meanings:

- `VERIFIED`: deterministic tests or repository contracts prove the item.
- `MACHINE_PASS`: a current runtime-bound machine run proves the item.
- `PENDING_EXTERNAL`: the required external production state does not exist.
- `PENDING_HUMAN`: deterministic gates exist, but real editorial judgment is required.
- `PENDING_REAL_RUN`: the implementation is tested, but a real production observation is required.

The current unresolved set is deliberately explicit: items 3, 37, 39, 50,
and 62. `python dragon_acceptance.py` remains the authoritative cutover gate
and must continue to return `BLOCKED` until all configured real-run, review,
scheduler, and activation evidence exists. Synthetic evidence never promotes
the editorial provider or substitutes for a real edition.

| # | Requirement | Status | Authoritative evidence | Remaining acceptance work |
| ---: | --- | --- | --- | --- |
| 1 | Preserve non-migrated production invariants | VERIFIED | `tests/test_v5_contract.py`; legacy regression tests | None for implementation; V4 remains active until cutover. |
| 2 | Historical editions remain unchanged | VERIFIED | `tests/test_v5_state.py::test_legacy_status_is_hashed_but_not_imported_as_complete`; finality guards | None; ordinary V5 runs are date-scoped and cannot rewrite historical completion. |
| 3 | Exactly one daily local Codex production schedule exists | PENDING_EXTERNAL | `config/local-automation.yaml`; `docs/LOCAL-CUTOVER.md`; fail-closed acceptance audit | Create and observe exactly one Codex local automation only after pre-cutover acceptance is ready. |
| 4 | No second production/evolution schedule is required | VERIFIED | `tests/test_v5_contract.py::test_one_local_orchestrator_contract`; `tests/test_v5_evolution.py::test_daily_evolution_is_thresholded_and_never_self_mutates` | None; evolution is an in-run stage/report. |
| 5 | One canonical run/resume entrypoint | VERIFIED | `dragon_daily.py`; `dragon_watchdog.py`; `tests/test_v5_contract.py::test_one_local_orchestrator_contract` | The future automation must invoke the documented watchdog command. |
| 6 | Duplicate schedule invocation is safe | MACHINE_PASS | `tests/test_v5_lock_watchdog.py::test_lock_is_exclusive_and_owner_releases_it`; chaos scenario `duplicate_schedule_invocation` | Scheduler trial must observe this with the actual automation. |
| 7 | Resume after crash is safe | MACHINE_PASS | `tests/test_v5_chaos.py::test_abrupt_process_interrupt_leaves_running_state_and_resume_reuses_upstream`; chaos scenario `resume_after_crash` | Human review of machine evidence remains required for cutover. |
| 8 | Africa/Casablanca publication date is correct | MACHINE_PASS | `tests/test_v5_scheduler_repair.py`; chaos scenario `casablanca_midnight` | Actual scheduler trial must retain this timezone. |
| 9 | Editorial role responsibilities remain internal | VERIFIED | `tests/test_v5_contract.py::test_executable_stage_graph_matches_authoritative_config`; `config/roles.yaml` | Real editorial output remains subject to items 37 and 39. |
| 10 | Canonical edition Markdown is Arabic | MACHINE_PASS | `tests/test_v5_synthetic_pipeline.py::test_synthetic_pipeline_creates_real_arabic_publications`; accepted `2099-03-23` fixture | Real edition remains covered by item 62. |
| 11 | Reader-facing article content is Arabic | VERIFIED | `tests/test_arabic_language_qa_v5.py::test_professional_arabic_passes`; `tests/test_v5_editorial_provider.py` | Real provider/human review remains covered by items 37, 39, and 62. |
| 12 | Cover reader-facing text is Arabic | VERIFIED | `tests/test_v5_publication.py::test_cover_renders_arabic_teaser_rail_without_corrupting_png`; shaping fail-closed test | Human visual comparison remains a cutover review requirement. |
| 13 | PDF reader-facing content is Arabic | MACHINE_PASS | accepted `2099-03-23` fixture; `tests/test_v5_publication.py::test_pdf_validator_rejects_non_arabic_reader_text` | Human visual comparison remains required. |
| 14 | EPUB reader-facing content is Arabic | MACHINE_PASS | accepted `2099-03-23` fixture; `tests/test_v5_epub.py::test_epub_is_deterministic_valid_reflowable_arabic` | Human artifact comparison remains required. |
| 15 | Arabic UTF-8 passes | VERIFIED | `tests/test_arabic_language_qa_v5.py::test_utf8_decode_is_strict` | None. |
| 16 | Arabic shaping passes | VERIFIED | `tests/test_v5_publication.py::test_cover_fails_closed_when_arabic_shaping_stops_working`; accepted fixture | Human raster review remains required. |
| 17 | RTL passes | VERIFIED | `tests/test_arabic_language_qa_v5.py`; `tests/test_v5_epub.py` | None for deterministic metadata/layout gates. |
| 18 | Mixed Arabic/Latin bidi fixtures pass | VERIFIED | `tests/test_v5_design_system.py::test_arabic_design_fixture_covers_mixed_direction_publication_cases`; Arabic QA tests | None. |
| 19 | PDF Arabic font/render test passes | MACHINE_PASS | accepted `2099-03-23` PDF and PDF QA; `tests/test_v5_publication.py` | Human contact-sheet review remains required. |
| 20 | EPUB RTL metadata/read direction passes | MACHINE_PASS | accepted `2099-03-23` EPUB; `tests/test_v5_epub.py::test_epub_rejects_wrong_direction_missing_cover_metadata_and_corrupt_zip` | None for deterministic validation. |
| 21 | Discovery is provider-based | VERIFIED | `tests/test_v5_discovery.py::test_registry_is_strict_and_truthful_about_availability` | Production providers must remain truthfully configured. |
| 22 | Important sources have provenance | VERIFIED | `tests/test_v5_discovery.py::test_trafilatura_adapter_extracts_bounded_html_with_provenance`; evidence graph tests | Real source review remains part of item 62. |
| 23 | Wire dependence can be detected | VERIFIED | `tests/test_v5_source_intelligence.py::test_source_intelligence_preserves_lineage_and_detects_wire_duplicates`; media critic tests | None. |
| 24 | Events are clustered | VERIFIED | `tests/test_v5_source_intelligence.py::test_layered_duplicate_detection_catches_rewritten_url_copies` | None. |
| 25 | Perspective/question engine works | VERIFIED | `tests/test_v5_research_planning.py::test_research_plan_is_stable_relevant_and_evidence_budgeted` | None. |
| 26 | Research budget works | VERIFIED | `tests/test_v5_research_planning.py::test_budget_policy_is_strict_config_and_context_is_bounded` | None. |
| 27 | Long research manages context | VERIFIED | `tests/test_v5_research_planning.py::test_budget_policy_is_strict_config_and_context_is_bounded`; continuity tests | Real provider trial must demonstrate usable output quality. |
| 28 | Important claims map to evidence | VERIFIED | `tests/test_v5_evidence_graph.py::test_claim_graph_maps_exact_evidence_and_confidence` | None. |
| 29 | Claim/source alignment rejects overstatement | VERIFIED | `tests/test_v5_evidence_graph.py::test_existing_citation_that_does_not_support_claim_fails_semantically`; adversarial-review test | None. |
| 30 | Media Critic exists | VERIFIED | `tests/test_v5_media_critic.py` | None. |
| 31 | Critical-thinking/adversarial review exists | VERIFIED | `tests/test_v5_editorial_gates.py`; bounded checklist and rejection tests | Real editorial quality remains covered by item 37. |
| 32 | Science integrity gates exist | VERIFIED | `tests/test_v5_science.py` | None. |
| 33 | Preprint, abstract-only, and full text are distinguished | VERIFIED | `tests/test_v5_science.py::test_science_gate_requires_honest_preprint_and_abstract_labels`; full-text passport test | None. |
| 34 | Persistent investigations survive days | VERIFIED | `tests/test_v5_investigations.py::test_investigation_dossier_survives_days_and_is_idempotent` | None. |
| 35 | Investigation graph edges have evidence | VERIFIED | `tests/test_v5_investigations.py::test_timeline_updates_and_material_uncertainty_blocks_publication` | None. |
| 36 | Unsupported accusations are structurally blocked | VERIFIED | `tests/test_v5_investigations.py::test_investigation_readiness_refuses_unsupported_accusation` | None. |
| 37 | Chief Editor produces coherent Arabic journalism | PENDING_HUMAN | deterministic structure/ranking gates in `tests/test_v5_editorial_gates.py`; provider trial is `NOT_RUN` | Complete a valid real provider trial and human review; do not infer coherence from fixtures. |
| 38 | No-news does not create filler | VERIFIED | `tests/test_v5_editorial_provider.py::test_no_news_is_explicit_and_cannot_create_filler` | None. |
| 39 | Editorial depth remains strong | PENDING_HUMAN | `tests/test_editorial_depth.py`; `tests/test_v5_editorial_provider.py` minimum-length gates | Human V4/V5 artifact comparison and real provider edition are required. |
| 40 | Cover is tied to final lead | VERIFIED | `tests/test_v5_design.py::test_cover_brief_rejects_wrong_date_masthead_and_unknown_teaser`; publication final gate | Human cover comparison remains required. |
| 41 | Hero art is separate from Arabic typography | VERIFIED | `tests/test_v5_design.py::test_cover_direction_separates_art_from_arabic_typography_and_is_stable` | None. |
| 42 | Multiple cover variants exist | VERIFIED | `tests/test_v5_design.py::test_all_cover_modes_expose_several_deterministic_variants` | None. |
| 43 | Cover fallback statuses are honest | VERIFIED | cover-direction and synthetic pipeline tests; asset classification tests | Real cover review remains required. |
| 44 | Interior pages use functional grammars | VERIFIED | `tests/test_v5_design.py::test_layout_uses_functional_page_grammars_without_editorial_authority`; design-system tests | Human visual comparison remains required. |
| 45 | Charts retain provenance | VERIFIED | `tests/test_v5_assets.py::test_chart_requires_data_provenance_units_period_axis_and_arabic_labels` | None. |
| 46 | Layout Doctor safely repairs or reverts | VERIFIED | `tests/test_v5_layout_doctor.py` | None. |
| 47 | PDF is generated and validated | MACHINE_PASS | accepted `2099-03-23` fixture; `tests/test_v5_publication.py` | Human visual review remains required. |
| 48 | EPUB is generated and EPUBCheck passes | MACHINE_PASS | accepted `2099-03-23`; W3C EPUBCheck 5.3.0, zero fatal/errors; `tests/test_v5_epubcheck.py` | Real edition validation remains part of item 62. |
| 49 | Existing GitHub publication finality remains correct | VERIFIED | `tests/test_automatic_publication.py`; `tests/test_scheduled_workflow_contract.py`; V4 fallback remains enabled | Retire V4 only through documented cutover. |
| 50 | Remote read-back verifies binaries | PENDING_REAL_RUN | exact-byte local-remote Git integration in `tests/test_v5_archive.py::test_git_archive_pushes_and_reads_back_exact_bytes` | Obtain a hash-bound archive receipt from the configured real remote for a production edition. |
| 51 | `PUBLICATION_COMPLETE` cannot lie | VERIFIED | `tests/test_v5_acceptance.py::test_publication_evidence_is_semantically_revalidated`; finality/tamper tests | None for implementation. |
| 52 | Publication and delivery states are separate | VERIFIED | `tests/test_v5_orchestrator.py::test_archive_failure_preserves_local_publication_and_retries_only_external_path`; reporting tests | Optional WhatsApp remains disabled. |
| 53 | Stage-local recovery works | MACHINE_PASS | `tests/test_v5_recovery.py`; all-stage boundary chaos test | Human review of the machine receipt remains required. |
| 54 | Idempotency is tested | MACHINE_PASS | synthetic resume/finality tests; chaos scenarios `resume_after_crash` and `already_complete_rerun` | None for deterministic behavior. |
| 55 | SHA conflict/concurrency behavior is tested | MACHINE_PASS | `tests/test_v5_archive.py::test_archive_refuses_stale_checkout_without_overwriting_remote_change`; chaos scenario `git_remote_change` | Real remote observation remains covered by item 50. |
| 56 | No mandatory paid LLM API dependency | VERIFIED | `tests/test_v5_contract.py::test_unconfigured_providers_are_not_claimed_available`; local-command provider configuration | Provider promotion requires explicit approval and evidence. |
| 57 | No dashboard is required | VERIFIED | `docs/LOCAL-AUTOMATION.md`; CLI status/reporting tests | None. |
| 58 | Dependency/license decisions are documented | VERIFIED | `docs/adr/ADR-007-open-source-component-matrix.md`; `docs/adr/ADR-008-openpaper-reference-architecture.md`; component-matrix test | None. |
| 59 | Runbooks match code | VERIFIED | `tests/test_v5_runbooks.py::test_required_failure_runbooks_are_complete`; failure catalog/recovery policy | Keep synchronized as codes change. |
| 60 | Full deterministic E2E fixture edition passes | MACHINE_PASS | accepted `2099-03-24` canonical synthetic run; `tests/test_v5_synthetic_pipeline.py` | Synthetic evidence does not satisfy item 62. |
| 61 | Chaos/recovery suite passes | MACHINE_PASS | `acceptance/machine/failure-injection/receipt.json`: 31 scenarios, 127 tests, runtime-bound PASS | Human review file is still absent and must not be fabricated. |
| 62 | One real or production-equivalent Arabic smoke edition passes | PENDING_REAL_RUN | fail-closed `python dragon_acceptance.py` reports `manual_real_publication: false` and provider unproven | Run a real provider-backed manual edition, human review it, then complete three unattended production dates. |
| 63 | Evolution metrics exist | VERIFIED | `tests/test_v5_evolution.py::test_daily_evolution_is_thresholded_and_never_self_mutates`; reporting metrics test | None. |
| 64 | Candidate improvements cannot auto-promote without benchmark | VERIFIED | `tests/test_v5_evolution.py::test_candidate_requires_improvement_without_any_dimension_regression` | Human-controlled promotion remains required. |
| 65 | Rollback exists | VERIFIED | Layout Doctor revert, atomic state backup, archive non-overwrite, and `docs/LOCAL-CUTOVER.md` rollback procedure | Actual cutover rollback is exercised only during scheduler trial if needed. |
| 66 | User feedback informs evaluation safely | VERIFIED | `tests/test_v5_evolution.py::test_feedback_is_queued_without_mutating_production` | None. |
| 67 | Owner only keeps the local execution host available | VERIFIED | `docs/LOCAL-AUTOMATION.md`; one-orchestrator contract and watchdog | This remains the documented normal operating responsibility after cutover. |

## Current acceptance facts

- The current regression baseline is 331 passed and 2 skipped.
- The current machine chaos receipt records 31 named scenarios and 127 passing
  targeted tests for runtime fingerprint
  `8970f1bad134bf429b9f0495ba68b5eb8d96dd0f96de819a012c619402de2bd4`.
- Synthetic date `2099-03-24` completed local publication with final QA `PASS`
  and W3C EPUBCheck 5.3.0 reporting zero fatal errors and zero errors.
- GitHub archive and WhatsApp delivery for that fixture are independently
  `DEGRADED`, as expected while both providers are disabled.
- Editorial provider status is `NOT_RUN`. The latest explicitly authorized live
  trial (`2026-09-10`, `attempt-150be12506fc4d1f8911d330b9b654cf`) preserved
  hash-bound raw research and both article attempts but failed
  `ARTICLE_SCHEMA_INVALID`: 3,499 validated active-article words against the
  required 4,000. It has no technically valid receipt and is not acceptance
  evidence; no promotion or human-review attestation may be fabricated from it.
- Human review evidence, the actual Codex automation, three consecutive
  unattended production runs, verified real-remote archive, activation flags,
  and cutover remain outstanding.
