# Creative Director & Publishing

role_id: publishing; can_spawn: none.
Task 4 owns compact cover direction and the durable canonical cover/brief, with visually verified SVG fallback when binary image archival is unavailable.
Task 5 owns semantic HTML, print CSS, XHTML, final manifest and publishing report. It preserves canonical prose exactly and waits for editorial/cover prerequisites.
Neither scheduled role generates PDF/EPUB or marks final publication COMPLETE. scripts/auto_publish.py handles deterministic rendering and exact GitHub binary read-back. Follow prompts/production-master.md and prompts/scheduled/.

For a version-4 editorial report, treat `daily-runs/YYYY-MM-DD/edition-plan.json`
and `config/edition-architecture.yaml` as canonical inputs. Preserve the
newspaper hierarchy in semantic HTML: section, article, standfirst, byline,
brief cluster, sidebar/data block and source navigation. Print layout expands
with content; it does not trim verified prose to imitate a fixed-length digest.
