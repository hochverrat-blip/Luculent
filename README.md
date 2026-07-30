# Luculent

Luculent is a document-targeted vocabulary study application. It extracts vocabulary from imported documents, divides larger documents into manageable sections, estimates readability, and uses spaced repetition to help users study unfamiliar words.

## Planned Features

- Import text from files or URLs
- Divide documents into independently studied sections
- Extract and store vocabulary in lemma form
- Track word difficulty, stability, and study status
- Estimate document-section readability
- Supports Korean initially

## MySQL

The project uses SQLite by default. To use MySQL, copy `settings.example.txt` to `settings.txt`, set `database=mysql`, and run
`docker compose up -d mysql`. The container listens on port 32000.
