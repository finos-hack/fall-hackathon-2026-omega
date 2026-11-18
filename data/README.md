# data/

## aigf-snapshot.json

A generated, minimal snapshot of the [FINOS AI Governance Framework](https://github.com/finos/ai-governance-framework) (AIGF) catalogue. The CLI uses it as the reference for risks, mitigations and use cases.

- **Source:** `finos/ai-governance-framework` at commit [`67b8c3257695d5ede09d262798bf28a0e58d4740`](https://github.com/finos/ai-governance-framework/tree/67b8c3257695d5ede09d262798bf28a0e58d4740). The commit is also recorded inside the file (`source.commit`).
- **Contents:** identifiers, titles, `doc-status` (with a `draft` flag), catalogue page URLs, each mitigation's `mitigates` list, and each use case's `related_risks`. **No body text** is copied.
- **Parse notes:** anything unusual found while parsing is listed in `parse_notes`. At this commit, `ri-2` and `ri-17` declare `related_risks` twice (first empty, then populated); the generator merges the lists and records a note.
- **Catalogue URLs** are derived from the AIGF site config (`docs/CNAME`, `docs/_config.yml`).

Do not edit the file by hand.

### Regenerate

From the repository root, with the project virtual environment active and a clean clone of AIGF at the pinned commit:

```bash
python scripts/build_aigf_snapshot.py ../sources/ai-governance-framework \
  --expect-commit 67b8c3257695d5ede09d262798bf28a0e58d4740
```

The script refuses to run if the clone is at a different commit or has local changes. Only `generated_at` should change when it is rerun at the same commit.

### Attribution

AIGF content: © FINOS, CC-BY-4.0. Source: <https://github.com/finos/ai-governance-framework> at commit `67b8c3257695d5ede09d262798bf28a0e58d4740`. License: <https://creativecommons.org/licenses/by/4.0/>. Changes: extracted IDs, titles, status, links and catalogue URLs into JSON; body text omitted.
