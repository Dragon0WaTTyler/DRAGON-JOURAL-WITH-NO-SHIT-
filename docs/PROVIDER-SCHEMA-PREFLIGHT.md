# Provider schema preflight and offline recheck

This follow-up used the offline-only objective at
`2f590a6a-70d8-4a88-97e8-cab032d154ff/goal-objective.md`. It made zero live
provider calls and performed zero research network retrievals. It did not enter
editorial, publication, delivery, or scheduler activation.

## Exact production boundary

The configured `LocalCommandEditorialProvider` builds the V5 payload through
`research_payload`. The Codex script's `prepare_codex_request` is the sole schema
serializer and prepares the prompt from that serialized payload. It uses the
existing hand-written `_schema`; no model-library schema generator intervenes.

`dragon/provider_schema.py` validates the serialized schema against the
[documented structured-output subset](https://developers.openai.com/api/docs/guides/structured-outputs)
and validates the V5 Arabic payload. Unsupported composition is rejected;
documented nested `anyOf`, nullable types, and local references are inspected.
Object required fields, additional-properties rules, formats, and schema size
limits are checked. This gate does not validate editorial evidence.

The one-shot wrapper prepares and checkpoints this contract before incrementing
its invocation counter. The provider passes the contract in a temporary file
bound to SHA-256. The subprocess validates its serialized schema, payload, and
prompt again without calling `_schema`. The bytes written to `--output-schema`
are checked against the preflight hash. A regression to unsupported composition
therefore fails before the client or one-call counter is used.

Offline boundary tests stub only the final Codex client. They also exercise the
real local-provider protocol subprocess with a fixture client, comparing schema
bytes and prompt hashes and rejecting a second invocation. Fixture client calls
are not live provider calls.

The pre-model HTTP 400 in the earlier October 4 trial came from explicit `allOf`
conditionals added under `hard_target_results.items`, not an inheritance or union
serializer. Commit `0e87e86` removed that composition. The runtime normalizer
still requires every hard target's disposition and enforces candidate/no-result
conditions, search attempts, source references, and semantic/current rationale.

## Saved schema proof

The provider-free diagnostic is retained under the shared Git directory:

`dragon/research-acceptance/offline-audits/schema-f865e736-0529-460c-8363-fac37d401e39/`

It contains the exact schema, payload, prompt, prepared request, preflight report,
and receipt with hashes. It uses the configured provider command without a
healthcheck or invocation; it makes no claim of current authentication or live
provider acceptance.

- Schema SHA-256: `fc54c1b215474defb0099201fb209f9ac225e00efd9ed836d5f1a7bf1b5fbf97`.
- Schema and payload preflight: PASS.
- Inspected composition/reference/definition/conditional keyword counts: all zero.
- Object properties: 67; maximum syntactic nesting: 7; enum values: 65.

## Hard-lane mechanism recheck

The original offline proof inventory was verified before its executable was
copied into a new exclusively created directory. A fresh comparison of Git
baseline `b8b4ffe` and the current scheduler is saved at:

`dragon/research-acceptance/offline-audits/hard-lane-a57df16b-06a0-4d53-8042-c0adee3d70d5/`

Both schedulers selected 8 actions under cap 8. The corrected scheduler selected
and executed fixture actions `ACT-41AA691D2B15` (PRIMARY suggestion) and
`ACT-65E84790E69A` (INDEPENDENT suggestion), reserving 2 slots and leaving 6 for
general scheduling. It displaced `ACT-E8E4553727A2` (an additional distinct-event
query) and `ACT-F2937C786654` (an additional accountability query). General
discovery and world research survived. Failed static retrievals created zero
source evidence. The deep-research configuration remains byte-identical to the
baseline.

This is `SYNTHETIC_FIXTURE_COMPARISON_NOT_SEP27_REPLAY`.
`SEP27_EXACT_REPLAY = UNAVAILABLE_MISSING_PRIMARY_ARTIFACTS`. No historical
packet was invented or reconstructed. The exact September 27 provider-yield
failure and scheduler decision remain unproven without their original inputs.

## Durability and completeness

New manifests report preserved-byte durability separately from bundle
completeness. The previous October 4 manifest and artifacts were verified
without modification. Its manifest hash remains
`d5e73b7f34f6d27c967a9f18d5057048f6ca2d5233bbfcaf95746a6c0f31c44f`.
The new derived receipt reports:

- `ACCEPTANCE_ARTIFACT_DURABILITY = PASS`.
- `ACCEPTANCE_BUNDLE_COMPLETENESS = INCOMPLETE_PROVIDER_REJECTED_REQUEST`.
- `FRESH_LIVE_REPLAY = NOT_APPLICABLE_NO_PROVIDER_PACKET`.

This records a schema rejection before a model packet, not a SERVICE omission
or a scheduler failure. Future diagnostics preserve complete redacted client
errors and exact raw output bytes when present.

## Test evidence and remaining boundary

The focused schema/provider/archive suite passed 71 tests. The hard-lane,
executor, recovery, and evidence suite passed 146 tests in 20.38 seconds. The
full suite passed 828 tests with 2 skips and zero failures in 232.18 seconds. Both skips require
WeasyPrint native libraries (`tests/test_automatic_publication.py:321` and `:327`).
The original hard-lane audit records 179 focused tests and 810 passing regression
tests before this follow-up. The 18 added cases cover schema compatibility,
counter/client blocking, both dispositions, real subprocess byte identity,
mutation rejection, and missing-response reporting.

Semantic, temporal, PRIMARY, independent-origin, source-family, exact-source
provenance, publication, action-budget, and provider-call gates remain intact.
Hard-lane priority provides an execution opportunity; existing qualification
alone can close a deficit. A future live trial requires separate authorization
after review of the deterministic evidence. Offline schema PASS is not a live
acceptance verdict.
