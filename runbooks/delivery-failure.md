# Delivery failure

## Symptoms
WhatsApp rejects, times out, or cannot confirm the idempotent document delivery.
## Failure codes
`WHATSAPP_SEND_FAILED`.
## Likely causes
Credential/recipient error, provider outage, attachment issue, or duplicate request ambiguity.
## Automatic actions
Retry the same idempotency identity and preserve redacted provider response.
## Fallback order
Same provider retry; operator notification; manual delivery after receipt audit.
## Data never to overwrite
PDF, manifest, successful recipient receipts, idempotency key, and provider evidence.
## Retry limit
Three delivery-only attempts.
## Stop condition
Stop on ambiguous prior success, invalid credentials, or exhausted retries.
## Resume behavior
Retry `whatsapp_delivery`; publication/archive states remain independent.
## Manual recovery
Exceptional only: confirm no prior delivery before sending once through an approved route.
