# Real pre-production runbook

This runbook is for the first real edition. It is not the production schedule.

## Start condition

- `origin/main` is current;
- Cloud environment has agent internet access enabled for approved research
  sources and GitHub persistence;
- secure GitHub authentication is configured in Cloud setup;
- `config/schedule.yaml` still says `enabled: false`;
- no smoke fixture is being reused as journalism.

## Run sequence

1. Chief Editor reads `memory/`, `investigations/`, `config/`, and all role
   contracts. Create `research/YYYY-MM-DD/`.
2. Run the nine research desks in parallel where supported. Each writes one
   JSON packet that conforms to `config/output-schema.json` and records URLs,
   dates, source type, and uncertainty.
3. Update persistent investigation dossiers only with evidence actually found;
   include evidence that could disprove the working hypothesis.
4. Chief Editor compares packets, removes duplicates, resolves conflicts,
   requests targeted follow-up, and writes one coherent Darija Latin draft.
5. Fact-check produces a report with `PASS`, `FIX`, or `REMOVE` for every
   material issue. Resolve all blocking findings.
6. Darija editor checks the final master. Any Arabic-script character is a
   hard failure. The editor must not change factual meaning.
7. Publishing creates the six required artifacts and updates README links.
8. Run:

   ```bash
   python scripts/validate_edition.py --date YYYY-MM-DD --mode preproduction
   ```

9. Inspect the actual Markdown, rendered PDF, EPUB structure, cover, sources,
   and manifest. Do not trust filenames alone.
10. Commit with subject `preproduction: YYYY-MM-DD`, push `origin/main`, and
    verify:

    ```bash
    git ls-remote origin refs/heads/main
    ```

The returned SHA must equal the local commit SHA. If any persistence step
fails, report `NOT COMPLETE` and retry only the failed persistence step.

## Required first-run labels

The master, cover metadata, and manifest must make clear:

```text
PRE-PRODUCTION — NOT YET DAILY PRODUCTION
```

The manifest must use `mode: preproduction`, `smoke_test: false`, and
`status: pre-production`. This prevents the real test from being mistaken for
an approved daily production edition.

## After the run

Record runtime and desk scores in the Cloud receipt. Review the edition itself
for weak Meknes reporting, unsupported Palestine claims, AI marketing claims,
overstated science, shallow History/Culture, English/French overuse, citation
gaps, and broken PDF/EPUB. Fix contracts or prompts before the fresh second
run. Do not enable the recurring schedule from this run.
