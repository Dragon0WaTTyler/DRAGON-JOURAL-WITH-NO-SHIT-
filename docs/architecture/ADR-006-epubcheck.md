# ADR-006: pin W3C EPUBCheck as a hard publication gate

- Status: accepted
- Date: 2026-09-08

## Decision

Run the official W3C EPUBCheck 5.3.0 Java distribution after DRAGON's internal
EPUB checks. Production preflight requires Java, the JAR, and the exact pinned
version. The run preserves the complete JSON report, validator version, JAR
SHA-256, exit code, counts, and message IDs. A fatal or error is a blocking
failure; file existence never implies conformance.

Official project and CLI documentation:

- <https://github.com/w3c/epubcheck>
- <https://w3c.github.io/epubcheck/docs/cli/>

## Evidence behind the decision

The first integration run found two defects that the internal validator did not:
CSS `direction` was forbidden in the EPUB style sheet, and
`page-progression-direction` was incorrectly placed on the package element.
After targeted fixes, the same full Arabic fixture passed with zero fatal,
error, and warning messages. This demonstrates that the external validator is
complementary rather than ceremonial.

## Distribution policy

The large official binary distribution is stored in the ignored local
`tools/epubcheck-5.3.0/` cache, not vendored into Git. Operators may override
the JAR with `DRAGON_EPUBCHECK_JAR`; the exact version check still applies.
