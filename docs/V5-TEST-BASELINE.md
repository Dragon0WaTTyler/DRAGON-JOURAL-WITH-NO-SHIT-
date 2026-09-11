# V5 current safe-test baseline

## Recorded baseline

On 2026-09-11, with generated machine evidence ignored, DRAGON ran:

```text
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider
```

Result: **380 passed, 2 skipped in 154.35 seconds**.

This command does not invoke an editorial provider, a production scheduler,
GitHub archive, or WhatsApp delivery. Test-only fixtures may create ignored
`2099-*` artifacts; their classification is defined in
`docs/ARTIFACT-CLASSIFICATION.md`.

## Coverage map

| Category | Principal tests |
| --- | --- |
| Unit/contracts | `test_v5_contract.py`, `test_v5_state.py`, `test_v5_config*` coverage through contract tests |
| Orchestration, locking, recovery | `test_v5_orchestrator.py`, `test_v5_lock_watchdog.py`, `test_v5_recovery.py`, `test_v5_chaos.py` |
| Source intelligence | `test_v5_discovery.py`, `test_v5_source_intelligence.py`, `test_v5_structured_extraction.py`, `test_v5_change_monitoring.py` |
| Research/editorial/evidence | `test_v5_deep_research.py`, `test_v5_research_planning.py`, `test_v5_research_recovery.py`, `test_v5_editorial_provider.py`, `test_v5_article_budgets.py`, `test_v5_evidence_graph.py`, `test_v5_editorial_gates.py` |
| Arabic, cover, layout | `test_arabic_language_qa_v5.py`, `test_v5_design*.py`, `test_v5_assets.py`, `test_v5_layout_doctor.py` |
| PDF/EPUB/finality | `test_v5_publication.py`, `test_v5_epub.py`, `test_v5_epubcheck.py`, `test_v5_synthetic_pipeline.py`, `test_v5_acceptance.py` |
| Archive/delivery mocks | `test_v5_archive.py`, `test_v5_whatsapp.py` |
| Investigation/evolution | `test_v5_investigation_scope.py`, `test_v5_investigations.py`, `test_v5_evolution.py`, `test_v5_continuity.py` |
| Legacy regression | `test_automatic_publication.py`, `test_scheduled_workflow_contract.py`, legacy publishing/reader-language tests |

The separate machine chaos receipt at
`acceptance/machine/failure-injection/receipt.json` records 34 scenarios and
152 passing targeted tests for the same current runtime fingerprint. It remains
machine evidence only until a human review is recorded.
