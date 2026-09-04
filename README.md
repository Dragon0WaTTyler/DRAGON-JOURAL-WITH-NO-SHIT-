# DRAGON Daily Newspaper

Five ChatGPT editorial jobs produce a daily Darija Latin newspaper. GitHub Actions validates and renders the archived sources to PDF and EPUB, then verifies the committed binary bytes before marking the edition published. No model API is used.

## Setup once

1. Replace the five existing ChatGPT scheduled prompts with the corresponding files in prompts/scheduled/ (see prompts/scheduled/README.md). Keep Africa/Casablanca. Cover is Task 4; Publishing is Task 5.
2. Merge this configuration on main and enable GitHub Actions with contents-write permission. Branch rules must allow github-actions[bot] publication commits. The workflow needs no PAT or model secret; it uses the repository GITHUB_TOKEN.
3. Run the five jobs once and inspect the first automatic edition. Configure supported recovery invocations for editorial jobs that miss prerequisites. An inactive or unsupported ChatGPT schedule cannot be repaired by the binary workflow.

The workflow reacts to ready package pushes and polls every 30 minutes for today/yesterday. No source package means no rendering. A failed validation is an Actions failure with an exact reason; the next invocation retries. Enable GitHub failed-workflow notifications in your account. GitHub schedules are best-effort and may be delayed or disabled after repository inactivity.

## Commands

python -m unittest discover -s tests -v
python scripts/validate_configuration.py
python scripts/auto_publish.py --check
python scripts/render_production_binaries.py --date YYYY-MM-DD
python scripts/auto_publish.py --date YYYY-MM-DD

Rendering alone never claims GitHub publication. The publisher requires a clean authenticated checkout, pushes normally (never force), fetches exact bytes, then commits verified final state and publication memory. Main-branch protection or missing write permission causes an explicit failure.

Canonical outputs: editions/YYYY/MM/YYYY-MM-DD/dragon-YYYY-MM-DD.pdf and .epub. The cover comes only from cover-brief.json. A persisted SVG fallback is valid and avoids an unsupported scheduled binary-image handoff. The original AI attempt remains honestly labelled.

See prompts/production-master.md, config/final-publication.yaml and docs/repair-audit.md. Historical smoke/preproduction files keep their original formats; scripts/run_pipeline.py is legacy and is not the production entry point.
