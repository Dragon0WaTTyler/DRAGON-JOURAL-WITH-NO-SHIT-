# Daily Newspaper

Cloud-first daily newspaper pipeline. GitHub is the persistent source of
truth; generated editions are archived under `editions/YYYY/MM/YYYY-MM-DD/`.

## Latest edition
2026-09-02

- [Markdown](editions/2026/09/2026-09-02/edition.md)
- [PDF](editions/2026/09/2026-09-02/edition.pdf)
- [EPUB](editions/2026/09/2026-09-02/edition.epub)

## Cloud smoke test

The first cloud run intentionally creates a synthetic edition so we can test
the full persistence path without making real editorial claims:

```bash
python scripts/publish_smoke_edition.py --date 2026-09-02
python scripts/validate_edition.py --date 2026-09-02
```

The authoritative success condition is:

```text
artifact validation PASS
git commit PASS
git push PASS
```

If any one of these fails, the run is `NOT COMPLETE`.

## Archive contract

Every published edition contains:

- `edition.md` — master text
- `edition.pdf` — fixed-layout output
- `edition.epub` — reflowable output
- `cover.webp` — editorial cover asset
- `sources.json` — source record
- `manifest.json` — machine-checkable publication state

See [`SPEC-v1.md`](SPEC-v1.md) for roles, gates, and the cloud-only
architecture.
