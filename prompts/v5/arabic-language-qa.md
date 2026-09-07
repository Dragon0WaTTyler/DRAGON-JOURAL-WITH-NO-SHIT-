# V5 Arabic Language QA stage

Read only the fact-checked canonical edition and its source mapping. Improve
professional Arabic grammar, headline quality, clarity, flow, repetition, and
typography without changing a fact, number, attribution, citation, uncertainty,
or source identifier. Do not transliterate the newspaper into Latin script.
Official technical names may retain their normal spelling when needed.

The configured byline is editorial attribution, not a claim of field reporting.
Never introduce an interview, quotation, eyewitness claim, or physical access
that is absent from the fact-checked input.

Return the edited canonical text plus a structured report. The deterministic
runner, not this prompt, decides completion from these gates:

- `ARABIC_LANGUAGE`
- `RTL`
- `UTF8`
- `ARABIC_RENDERING`
- `MOJIBAKE`
- `FOREIGN_LANGUAGE_LEAKAGE`

If a factual change appears necessary, do not make it here. Return the smallest
affected article to `factcheck` with a precise reason.
