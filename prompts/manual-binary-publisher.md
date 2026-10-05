# Optional manual recovery

> Scope: retained V4/legacy tooling. The current V5 target is `SPEC-v5.md`
> and one local Codex trigger producing Arabic. These instructions remain
> applicable only to the legacy fallback; retirement requires `docs/LOCAL-CUTOVER.md`.


Normal publication is automatic through .github/workflows/publish.yml.
For recovery, read prompts/production-master.md and config/final-publication.yaml, install requirements, then use a clean authenticated checkout of main:

python scripts/auto_publish.py --date YYYY-MM-DD

For local validation/rendering only:

python scripts/render_production_binaries.py --date YYYY-MM-DD

The latter writes a PENDING binary-render-report.json and never declares publication. Do not edit source prose or redesign the cover. A persisted AI_GENERATED or SVG_FALLBACK is accepted according to current policy. Inspect recovered PDFs visually if performing manual recovery, and record that observation separately from automated structural checks.
