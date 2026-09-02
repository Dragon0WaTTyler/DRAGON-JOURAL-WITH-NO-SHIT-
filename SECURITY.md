# Security and credential rotation

## Cloud-only credential rules

- GitHub authentication is configured as a hosted Codex Cloud secret.
- Never print `GITHUB_TOKEN`, include it in a commit, or copy it into a
  research packet, receipt, artifact, or log.
- The temporary askpass helper and token file must be removed by Cloud setup
  cleanup. They are not part of the repository contract.
- The token must remain limited to this repository and the permissions needed
  to push `main`.

## Rotation checklist

The current token is documented as expiring on **2026-10-02**. Rotate it before
that date in the hosted Cloud environment:

1. Create a replacement fine-grained GitHub token limited to this repository
   and the minimum required contents permission.
2. Replace the Cloud secret; do not put the value in this repository.
3. Run a hosted Cloud smoke or pre-production task that performs a safe push
   and exact `git ls-remote origin refs/heads/main` verification.
4. Confirm the receipt contains only SHAs and status fields, never a token.
5. Revoke the expired token and record the rotation date in the Cloud secret
   owner’s operational notes.

If authentication or remote verification fails, the edition status is
`NOT_COMPLETE` even when the artifacts were generated successfully.
