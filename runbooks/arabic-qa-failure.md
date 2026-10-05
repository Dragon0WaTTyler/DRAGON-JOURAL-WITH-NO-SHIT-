# Arabic QA failure

## Symptoms
Mojibake, reversed RTL, foreign-language leakage, broken shaping, or inconsistent terminology.
## Failure codes
`ARABIC_LANGUAGE_QA_FAILED`, `ARABIC_RENDERING_FAILED`, `RTL_LAYOUT_FAILED`.
## Likely causes
Encoding/font/runtime fault, mixed-direction markup, or provider-language leakage.
## Automatic actions
Repair language/typography only; facts and evidence mapping are immutable.
## Fallback order
UTF-8 repair; terminology repair; font/layout repair; block.
## Data never to overwrite
Claims, numbers, quotations, sources, and accepted editorial meaning.
## Retry limit
Two targeted attempts.
## Stop condition
Stop if a language repair could change facts or Arabic remains unreadable.
## Resume behavior
Retry `arabic_language_qa`, publication source, or PDF according to the defect.
## Manual recovery
Exceptional only: native Arabic editorial review with recorded changes.
