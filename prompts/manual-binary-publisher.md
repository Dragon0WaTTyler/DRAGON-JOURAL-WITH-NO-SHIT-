# Optional manual recovery

Normal publication is automatic through .github/workflows/publish.yml.
For recovery, read prompts/production-master.md and config/final-publication.yaml, install requirements, then use a clean authenticated checkout of main:

python scripts/auto_publish.py --date YYYY-MM-DD

For local validation/rendering only:

python scripts/render_production_binaries.py --date YYYY-MM-DD

The latter writes a PENDING binary-render-report.json and never declares publication. Do not edit source prose or redesign the cover. A persisted AI_GENERATED or SVG_FALLBACK is accepted according to current policy. Inspect recovered PDFs visually if performing manual recovery, and record that observation separately from automated structural checks.
