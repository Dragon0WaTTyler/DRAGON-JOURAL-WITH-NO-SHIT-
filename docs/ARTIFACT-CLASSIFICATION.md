# DRAGON artifact classification

## Source-controlled historical production evidence

Version 4 historical editions and their dated `daily-runs/YYYY-MM-DD/` records
are committed when they are part of the established production history. They
must not be rewritten by V5 work, tests, or retries.

## Local machine evidence

`acceptance/` is ignored because it contains hash-bound local machine receipts,
provider-trial raw records, and review material. It is retained locally for
human review and must never be treated as a source-controlled production
archive or as an accepted publication merely because files are present.

## Synthetic test artifacts

The date range `2099-*` is reserved for explicit synthetic fixtures. Generated
paths under `daily-runs/2099-*`, `editions/2099/`, and
`evolution/reports/2099-*.json` are ignored. They may prove deterministic
behavior when their run report and runtime fingerprint validate, but they can
never satisfy a production, archive, delivery, or cutover gate.

Synthetic investigation dossiers use the generated `investigations/CASE-*`
namespace and are ignored. Curated investigation seeds remain explicitly
tracked by name.

## Temporary data

`tmp/` is disposable local diagnostics. It is neither publication evidence nor
a fixture contract.

## Operational rule

Production evidence must declare its mode, edition date, runtime fingerprint,
artifact hashes, and relevant read-back or human-review status. Generated files
do not alter a completed historical edition, and ignored local material must
not be force-added merely to make a working tree look clean.
