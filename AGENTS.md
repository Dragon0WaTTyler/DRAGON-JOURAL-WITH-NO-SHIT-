# Daily Newspaper — cloud smoke test

This repository is the source of truth for the Daily Newspaper project.

## Current task

This is an architecture smoke test, not a real news edition. Do not present
the fixture as reporting and do not publish real-world claims from it.

For the requested test date, run:

```bash
python scripts/publish_smoke_edition.py --date YYYY-MM-DD
python scripts/validate_edition.py --date YYYY-MM-DD
```

The run is complete only when validation passes, a commit succeeds, and the
commit is pushed to `origin`. If push fails, report `NOT COMPLETE` and retry
the push without regenerating the edition.

## Cloud-only constraints

- Work only inside this repository checkout.
- Use network access only for the approved source-control operation and the
  explicitly requested smoke-test checks.
- Never use a local machine path, localhost service, or a process that must
  remain running after this task.
- Keep the fixture clearly labeled as `SMOKE TEST — NOT FOR PUBLICATION`.
- Do not rewrite or delete existing history.

## Required commit

Use exactly this commit subject for the first run:

```text
edition: YYYY-MM-DD
```

Before committing, show the validation result and the exact files included.
