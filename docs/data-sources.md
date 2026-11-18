# Data sources

Upstream sources this project reads. Each was inspected on 2026-11-18. Every ID used in this project must trace back to a file at the commit listed here.

Local clones live **outside** this repository in `../sources/` and are not committed.

## Summary

| # | Source | Commit | License | Role |
|---|--------|--------|---------|------|
| 1 | [finos-hack/ai-steel-thread-demo](https://github.com/finos-hack/ai-steel-thread-demo) | `2782173d47f5074f8767dbdf553fa9165ee1ccd8` (branch `main`, 2026-08-11) | **None declared** (no LICENSE file; GitHub API `license: null`) | Input: CALM architecture and control requirements |
| 2 | [finos/ai-governance-framework](https://github.com/finos/ai-governance-framework) | `67b8c3257695d5ede09d262798bf28a0e58d4740` (branch `main`, 2026-11-02, "v3-release") | **CC-BY-4.0** (see its `LICENSE` and `NOTICE`) | Reference catalogue: risks, mitigations, use cases |
| 3 | [finos/common-cloud-controls](https://github.com/finos/common-cloud-controls) | `00bb0a8ffb8c6894968d25e46e0bbe03f14c3919` (branch `main`, via GitHub API, not cloned) | **Community Specification License 1.0** (GitHub reports `NOASSERTION`) | Optional; not used in the first version |

## 1. Governance-as-Code Steel Thread (CALM architecture)

**Files used**

- `architecture/loan-approval.calm.json` is the CALM architecture. It is identical to `frontend/public/architecture/loan-approval.calm.json`.
- `architecture/url-to-local-file-mapping.json` maps `https://ai-steel-thread.local/control-requirement/*` URLs to local files.
- `architecture/controls/mi-{1,4,5,11}-*.requirement.json` are the control-requirement JSON Schemas.

**Shape**

- `$schema`: `https://calm.finos.org/release/1.2/meta/calm.json` (CALM **1.2**).
- 39 nodes, 30 relationships and 4 flows. Controls are attached to 11 nodes and 2 relationships; no flow has controls.
- `metadata[0]` links the architecture to AIGF use case `uc-3_loan-approval` and lists `aigf-mitigations: [mi-1, mi-4, mi-5, mi-11]` and `aigf-risks: [ri-1]`.
- Each `controls` object is keyed by a control name. Each entry has `description`, `aigf-mitigations`, `aigf-risks` and `requirements[]`. Each requirement has a `requirement-url` and an inline `config`, which includes `control-id` and `aigf-catalog-url`.

| Control key | `config.control-id` | `aigf-mitigations` | `aigf-risks` | Attached to |
|---|---|---|---|---|
| `ai-data-leakage-prevention` | mi-1 | mi-1 | ri-1 | 4 nodes + 2 relationships |
| `ai-system-observability` | mi-4 | mi-4 | ri-1 | 5 nodes |
| `system-acceptance-testing` | mi-5 | mi-5 | ri-4, ri-6, ri-14 | 3 nodes |
| `human-feedback-loop` | mi-11 | mi-11 | ri-1, ri-6 | 4 nodes |

The architecture contains no Common Cloud Controls (`CCC.*`) IDs.

**Validation:** `calm validate` with `@finos/calm-cli` 1.73.0 reports 0 errors and 0 warnings. See [calm-validate-baseline.txt](./calm-validate-baseline.txt).

**Extraction:** Load the JSON with the Python standard library. Walk `nodes[]`, `relationships[]` and `flows[]`, and emit one row per (element, control key, requirement), carrying the control's `aigf-risks` and `aigf-mitigations` lists. The project reads the file from a path the user supplies. Because no license is declared, **we do not copy it into this repo**.

## 2. FINOS AI Governance Framework (AIGF)

**Files used**

- `docs/_risks/ri-*.md`: **24 risks**, one Markdown file each, defined in YAML front matter. IDs are `ri-N` and are not contiguous (1, 2, 4–10, 14, 16–20, 22–30). One risk (ri-30) is `Draft`.
- `docs/_mitigations/mi-*.md`: **25 mitigations**, IDs `mi-1` to `mi-25`. Two (mi-24, mi-25) are `Draft`.
- `docs/_usecases/uc-3_loan-approval.md`: front matter lists `related_risks` (ri-1, ri-4, ri-6, ri-14, ri-17, ri-19) and `related_mitigations` (mi-1, mi-4, mi-5, mi-11).

**Fields**

- Risk front matter: `sequence`, `title`, `layout`, `doc-status`, `type` (RC/SEC/OP), `domain`, `related_risks` (risk → risk), plus optional `*_references` lists (OWASP, NIST, EU AI Act, FFIEC, ATR, IOSCO, Canada, UK).
- Mitigation front matter: `sequence`, `title`, `layout`, `doc-status`, `type` (PREV/DET), `domain`, **`mitigates`** (mitigation → risks), `related_mitigations`, plus `*_references` (ISO 42001, NIST SP 800-53r5, IOSCO, EU AI Act, ATR).
- The risk ↔ mitigation link exists in the source **in one direction only**: `mitigation.mitigates`. Risk files have no mitigation list.

**Machine-readable export:** None found. There are no JSON, CSV or MCP data files in the repo. `docs/_data/*.yml` holds taxonomies (use cases, deployment models, data classification), not the catalogue.

**Extraction:** Parse the YAML front matter of each `ri-*`, `mi-*` and `uc-*` file, keeping only `id` (from the filename), `title`, `type`, `domain`, `doc-status`, `mitigates`, `related_risks` and `related_mitigations`. Save the result as a small generated JSON snapshot with the source commit SHA. Body text is not copied.

- Parser caveat: `ri-17` **and `ri-2`** each declare `related_risks` twice (first empty, then populated), so a strict YAML loader that rejects duplicate keys will fail on them. PyYAML `safe_load` silently keeps the last value. Our loader merges the lists and records a parse note (checked by a full scan of `docs/_*/*.md` on 2026-11-18; no other duplicate keys).
- `docs/_usecases/uc-index.md` is a taxonomy page with no front matter, not a use case. All four use cases (uc-1 to uc-4), including `uc-3_loan-approval`, are `doc-status: Draft`.
- The catalogue site is `https://air-governance-framework.finos.org/` (the repo's `docs/CNAME`). The Steel Thread's `aigf-catalog-url` values point there.

## 3. Common Cloud Controls (optional, not used yet)

- Machine-readable YAML catalogues live in `catalogs/**/{controls,threats,capabilities,metadata}.yaml` (134 files), in the Gemara format.
- ID format: `CCC.Core.CN01` for controls and `CCC.GenAI.TH01` for threats.
- `catalogs/ai-ml/gen-ai/mappings/threats-finos-aigf.yaml` maps CCC GenAI threats to AIGF.
- This could enrich the workbook later. It is not needed for Track 2 because the Steel Thread architecture references no CCC IDs.

## Attribution

- AIGF content (IDs and titles only) © 2025 FINOS, licensed under [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).
- The Steel Thread is referenced by URL and commit only; none of its files are copied here.
