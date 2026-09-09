# ADR-010: Python runtime dependency and license record

- Status: accepted
- Audit date: 2026-09-09
- Scope: every direct package range in `requirements.txt`

## Decision

Keep the current eleven direct Python dependencies. They support deterministic
local parsing, validation, Arabic shaping, PDF/EPUB production, and timezone
handling without adding a daemon, scheduler, paid API, or credential. Do not
vendor their source or silently widen their major-version ranges.

The licenses below were read from the installed distributions' metadata and
license files during this audit. Version ranges remain authoritative in
`requirements.txt`; an upgrade must repeat the license and Arabic/runtime
regression review. Transitive packages remain governed by their own bundled
notices and must be included by any binary redistributor.

| Direct package | Audited install | License | Runtime role | Failure impact and fallback |
| --- | --- | --- | --- | --- |
| `Pillow` | 12.2.0 | MIT-CMU | Canonical cover, Windows Arabic PDF raster pages, contact sheets | Blocking for local cover/PDF; preflight fails rather than emitting placeholders. |
| `reportlab` | 5.0.1 | BSD-style | Searchable Arabic PDF text overlay and source links | Blocking for searchable Windows PDF; no silent raster-only publication. Bundled font files retain their own notices. |
| `pypdf` | 6.14.2 | BSD-3-Clause | PDF assembly, inspection, cover identity, extraction, links | Blocking for PDF and final QA. |
| `PyYAML` | 6.0.3 | MIT | Strict local configuration loading | Blocking preflight/configuration failure. |
| `jsonschema` | 4.26.0 | MIT | Provider, source, investigation, and manifest schema validation | Blocking for affected contract; never accept unvalidated data. |
| `weasyprint` | 68.1 | BSD-3-Clause | Protected V4/Linux renderer and non-Windows compatibility path | V5 Windows uses the Pillow/ReportLab path; V4/Linux tests remain protected until cutover. |
| `markdown-it-py` | 4.2.0 | MIT plus bundled markdown-it notice | Markdown parsing in protected publication tooling | Block the affected publication-source path if unavailable. |
| `tzdata` | 2026.3 | Apache-2.0 | Reproducible IANA timezone data, including Africa/Casablanca | Blocking date/time preflight; never fall back to naive local time. |
| `arabic-reshaper` | 3.0.1 | MIT | Arabic contextual shaping for raster output | Blocking Arabic rendering failure; fail closed on unshaped output. |
| `python-bidi` | 0.6.10 | LGPL-3.0 plus bundled third-party notices | Unicode bidirectional display ordering | Blocking Arabic rendering failure. Keep as an unmodified replaceable dependency and preserve LGPL/third-party notices in redistribution. |
| `trafilatura` | 2.2.0 | Apache-2.0 | Bounded ordinary-HTML extraction | Source-local failure; route only eligible material to another approved adapter or skip. |

## Compatibility and operational impact

- Arabic/RTL: `arabic-reshaper`, `python-bidi`, Pillow, ReportLab, and pypdf are
  exercised together by the Arabic cover/PDF fixtures and synthetic edition.
- Local scheduler: every dependency is in-process or CLI-local; none creates a
  scheduler, background daemon, dashboard, or competing state machine.
- APIs and keys: none of these packages requires a paid API or credential.
- Licensing: no AGPL or non-commercial dependency is directly required.
  `python-bidi` is the only direct copyleft dependency and remains dynamically
  replaceable/unmodified; distributions must retain its LGPL-3.0 and bundled
  third-party notices and provide any corresponding obligations applicable to
  the form distributed.
- Failure posture: preflight and stage validators report unavailable required
  dependencies honestly. No missing library may be treated as publication
  success.

## Upgrade rule

For any direct dependency major-version change:

1. inspect the new distribution metadata and license files;
2. update this ADR's audited version/license if changed;
3. run the full regression, deterministic synthetic publication, Arabic PDF
   visual/structural checks, EPUBCheck, and chaos suite as applicable;
4. regenerate runtime-bound evidence because `requirements.txt` participates
   in the runtime fingerprint.
