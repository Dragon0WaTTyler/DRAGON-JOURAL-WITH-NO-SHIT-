# DRAGON — Manual Final Binary Publisher

This is a MANUAL Codex Cloud handoff. It is not one of the five Scheduled Work jobs and must not be scheduled.

## Mission

Turn an already-complete publication-source package into final validated PDF and EPUB binaries without changing editorial content.

## Required inputs

For `YYYY-MM-DD`, require:

- `editions/YYYY/MM/YYYY-MM-DD/edition.html`
- `editions/YYYY/MM/YYYY-MM-DD/print.css`
- `editions/YYYY/MM/YYYY-MM-DD/epub-content.xhtml`
- `editions/YYYY/MM/YYYY-MM-DD/manifest.json`
- the canonical cover path declared by the manifest
- `daily-runs/YYYY-MM-DD/publishing-report.json`
- `daily-runs/YYYY-MM-DD/status.json`

Require `publication_source_package == COMPLETE`.

## Cover hard gate

A generated cover and an SVG fallback are not the same thing.

- If the manifest says `cover_asset_type: SVG_FALLBACK`, normal final publication is BLOCKED.
- Do not rename an SVG fallback to WEBP/PNG and do not claim image generation succeeded.
- Do not redesign or fabricate a different cover inside the binary publisher.
- Historical emergency repair may use `--allow-svg-fallback`, but the resulting status must remain visibly distinct from a normal generated-cover publication.

## Rendering command

Install repository requirements, then run:

```bash
python scripts/render_production_binaries.py --date YYYY-MM-DD
```

For an explicit historical fallback repair only:

```bash
python scripts/render_production_binaries.py --date YYYY-MM-DD --allow-svg-fallback
```

## PDF contract

- Page 1: canonical cover exactly.
- Page 2 onward: canonical `edition.html` rendered with canonical `print.css`.
- Output path: `editions/YYYY/MM/YYYY-MM-DD/dragon-YYYY-MM-DD.pdf`.
- Validate non-zero size, readable PDF structure, and page count >= 2.
- Visually inspect the rendered PDF. Reject clipping, overlap, blank content pages, mojibake, or a missing/incorrect cover.

## EPUB contract

- Package canonical `epub-content.xhtml` without editorial rewriting.
- Package the canonical cover using its real media type.
- Output path: `editions/YYYY/MM/YYYY-MM-DD/dragon-YYYY-MM-DD.epub`.
- Validate EPUB mimetype placement, ZIP structure, OPF/container/nav XML, cover metadata, and non-zero size.

## Persistence

After successful render and validation:

1. Review the metadata updates made by the renderer.
2. Commit the PDF, EPUB, and changed JSON metadata to the repository.
3. Read back the committed paths from GitHub.
4. Do not report final publication COMPLETE unless both binaries exist in GitHub and passed validation.
5. If the cover gate failed, keep final publication blocked even if the publication-source package is complete.

## 2026-09-04 repair note

The canonical source package is complete, but the cover is currently `SVG_FALLBACK` because image generation failed. Therefore the normal command must block. Fix the generated cover first for a true final publication. Use the fallback flag only if the user explicitly accepts a degraded historical repair.
