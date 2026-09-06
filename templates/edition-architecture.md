# DRAGON edition architecture — version 4

The Chief Editor first writes `daily-runs/YYYY-MM-DD/edition-plan.json`, then
writes the reader-facing edition. The plan is an editorial decision record, not
reader prose.

## Plan shape

```json
{
  "date": "YYYY-MM-DD",
  "timezone": "Africa/Casablanca",
  "edition_architecture_version": 4,
  "edition_word_budget": 12000,
  "sections": [
    {
      "section_id": "siyasa_dawla",
      "status": "ACTIVE",
      "editorial_reason": "Verified parliamentary decision with public impact.",
      "articles": [
        {
          "story_id": "morocco-example",
          "headline": "Exact reader-facing H3 headline",
          "format": "lead_article",
          "word_budget": 1200
        }
      ]
    },
    {
      "section_id": "se77a",
      "status": "SKIPPED",
      "skip_reason": "No fresh, verified health development after the required source sweep."
    }
  ]
}
```

Every section from `config/edition-architecture.yaml` appears exactly once.
Use `ACTIVE` only for supported material. `SKIPPED` records why there is no
verified reader-facing item that day; it never authorizes filler.

## Reader-facing Markdown shape

```markdown
## Siyasa w Dawla

### Exact reader-facing H3 headline

*Standfirst kaygol l-khabar w l-ahammiyya dyalo b-jomla wa7da.*

Tahrir: DRAGON

Lead paragraph...

Nut graf kaychar7 3lach had l-khabar mohim daba...

Facts, context, opposing evidence ila kayn, uncertainty, consequences, w chno jay. [S01] [S02]

### Briefs

#### Brief headline wa7d

80-200 kelma b-source IDs. [S03]
```

Use one H2 for each ACTIVE section and the exact H3 headlines recorded in the
plan. Leads and standard articles need a standfirst and `Tahrir: DRAGON`.
Opinion is visibly labelled `Ra2y`; it never impersonates reporting.
