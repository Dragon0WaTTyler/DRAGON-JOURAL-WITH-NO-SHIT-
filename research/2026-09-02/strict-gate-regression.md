# Strict long-form gate regression

Before regenerating the two long-form sections, the current 2026-09-02 edition was validated with:

```text
python scripts/validate_edition.py --date 2026-09-02 --mode preproduction
```

Expected result after removing the HOLD bypasses:

```text
VALIDATION FAIL (preproduction)
history section has 56 words; hard minimum is 800
literature_culture section has 144 words; hard minimum is 800
```

This failure is intentional and proves that HOLD cannot override either core long-form minimum.
