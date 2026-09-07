# DRAGON Daily Newspaper

DRAGON V5 is migrating to one resilient local Windows production workflow that
creates a professional Arabic newspaper, validates PDF and EPUB locally,
archives it to GitHub, and optionally delivers it through a configured WhatsApp
provider. The migration preserves the proven Version 4 editorial architecture
and deterministic publication safeguards without introducing a paid model API.

## Current migration status

V5 is the authoritative implementation target, but cutover has not happened.
The existing five ChatGPT Scheduled Work jobs and GitHub binary publisher remain
the temporary production fallback while the local system is built and tested.
They must not be disabled until the acceptance steps in
`docs/LOCAL-CUTOVER.md` pass.

- V5 contract: `SPEC-v5.md`
- Local operating contract: `docs/LOCAL-AUTOMATION.md`
- Migration audit: `docs/LOCAL-MIGRATION-AUDIT.md`
- Legacy V4 contract: `SPEC-v1.md`

## V5 architecture

One Windows scheduler entry starts `python dragon_daily.py`. The orchestrator
owns preflight, research, article generation, chief editing, fact-checking,
Arabic language QA, cover, publication sources, PDF, EPUB, final QA, GitHub
archive, and WhatsApp delivery. One atomic daily state file records checkpoints,
attempts, failures, hashes, publication status, archive status, and delivery
status.

Reader-facing output is Arabic (`lang="ar"`, `dir="rtl"`). Articles retain the
Version 4 newspaper structure: substantial leads, varied supporting formats,
explicitly active or skipped sections, exact sources, and flexible page count.

AI-dependent editorial work and WhatsApp delivery are provider-backed. Missing
or untested providers are reported as unavailable; the project does not invent
credentials, enable billing, or claim unattended operation without proof.

## Existing V4 commands

These remain available during migration and apply only to the legacy runtime:

```text
python scripts/validate_configuration.py
python scripts/auto_publish.py --check
python scripts/render_production_binaries.py --date YYYY-MM-DD
python scripts/auto_publish.py --date YYYY-MM-DD
```

`scripts/run_pipeline.py` is legacy pre-production tooling and is not the V5
entry point. Historical editions retain their original language, filenames,
manifests, and status semantics.

## Development verification

```text
python -m unittest discover -s tests -v
```

The native WeasyPrint render smoke test may be skipped on an unsupported local
Windows installation. V5 preflight must prove the configured Arabic-capable PDF
runtime before local production can be declared ready.
