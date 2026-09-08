# Document parse failure

## Symptoms
PDF, Office, dataset, or table material cannot be parsed through its routed parser.
## Failure codes
`SOURCE_MATERIAL_ROUTE_REQUIRED`, `DOCUMENT_PARSE_FAILED`.
## Likely causes
Wrong MIME type, corrupt/encrypted document, unsupported structure, or missing parser.
## Automatic actions
Classify material first, invoke only the matching bounded parser, and preserve parse diagnostics.
## Fallback order
Native structured parser; accessible official alternative; text layer/OCR when authorized; skip.
## Data never to overwrite
Original bytes/hash, MIME, source URL, license note, and earlier successful parse.
## Retry limit
One parse per approved route and one safe alternate.
## Stop condition
Stop on corruption, encryption, rights uncertainty, or unverifiable OCR.
## Resume behavior
Retry only the document/source unit and dependent claims.
## Manual recovery
Exceptional only: approve OCR, credentials, or a new parser after provenance review.
