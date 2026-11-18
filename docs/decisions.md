# Decisions and next tasks

Decisions made on 2026-11-18, following the data-sourcing findings in [data-sources.md](./data-sources.md). Read this file first when resuming work.

## D1. Licensing and source handling

- **Steel Thread** ([finos-hack/ai-steel-thread-demo](https://github.com/finos-hack/ai-steel-thread-demo), pinned at `2782173d47f5074f8767dbdf553fa9165ee1ccd8`) declares no license, so **none of its files are copied into this repo**.
  - The CLI takes the CALM architecture path as an input argument.
  - Unit tests use a small **synthetic fixture we write ourselves**, labelled as such in the file.
  - The demo runs against a local clone at `../sources/ai-steel-thread-demo`.
  - CI (later) clones the Steel Thread at the pinned SHA during the workflow and never commits it.
  - A license request to upstream is drafted in [upstream-issue-license.md](./upstream-issue-license.md), for the maintainer to post.
- **AIGF** ([finos/ai-governance-framework](https://github.com/finos/ai-governance-framework) @ `67b8c3257695d5ede09d262798bf28a0e58d4740`, CC-BY-4.0):
  - We commit only a generated snapshot of IDs, titles, types, `mitigates` / related links and catalogue URLs. No body text.
  - It is attributed as "© FINOS, CC-BY-4.0" in `data/README.md` and `NOTICE`. That attribution is added together with the snapshot.
- **Common Cloud Controls**: out of scope for the first version.

## D2. Mapping model

- **No hand-written mapping file.** Each control's claimed links come from its own `aigf-risks` and `aigf-mitigations` fields in the CALM architecture.
- **Expected risks** come from the AIGF use case named in the architecture metadata (`finos-use-case`): its `related_risks`. For the Steel Thread this is `uc-3_loan-approval` → ri-1, ri-4, ri-6, ri-14, ri-17, ri-19.
- **Evidence** is labelled **"declared"**. It is the control's `requirement-url` plus inline `config` from CALM. Runtime evidence is not verified.

## D3. Coverage views and CI rule

| View | Definition | Current Steel Thread result | Severity |
|---|---|---|---|
| Claims-based gaps | expected risks − risks claimed by any control (`aigf-risks`) | **ri-17, ri-19** | **Error: fails CI** |
| Catalogue-implied gaps | expected risks − risks in AIGF `mitigates` of any mitigation used | ri-17 | Info (shown in workbook) |
| (a) Unsupported claim | a control claims mitigation *m* addresses risk *r*, but AIGF *m*.`mitigates` doesn't include *r* | `human-feedback-loop`: mi-11 → ri-1 | Warning |
| (b) Possibly covered, not claimed | an expected risk is in the `mitigates` list of a mitigation the architecture uses, but no control claims it | ri-19 via mi-4 | Warning |

`check` exits non-zero only when claims-based gaps exist. Warnings are printed and written to the workbook but don't change the exit code.

## D4. Package layout (Python 3.10+, developed on 3.14)

```
pyproject.toml            # name gac-workbook; deps: openpyxl, pyyaml; console script `gac-workbook`
src/gac_workbook/
  calm.py                 # load CALM 1.2 JSON → ControlUse rows (element, control key, risks, mitigations, requirement-url, config)
  aigf.py                 # parse AIGF front matter (ri/mi/uc) or load the data/ snapshot
  coverage.py             # expected vs claimed vs catalogue-implied; findings (a) and (b)
  workbook.py             # openpyxl: Summary, Traceability, Gaps, Findings, Sources sheets
  cli.py                  # `export` and `check` subcommands
data/aigf-snapshot.json   # generated from AIGF @ pinned SHA
data/README.md            # provenance + CC-BY-4.0 attribution
tests/fixtures/           # synthetic CALM fixture (ours, labelled)
tests/test_*.py           # pytest
```

AIGF parsing caveat: `ri-17` repeats the `related_risks` key. Use a loader that tolerates duplicate keys (PyYAML `safe_load` keeps the last one), or merge the values.

## Next tasks (in order)

1. **Environment:** create `.venv` (`python -m venv .venv`, then `source .venv/Scripts/activate` in Git Bash) and `pyproject.toml`; install openpyxl, pyyaml and pytest.
2. **AIGF snapshot:** write a generator script that reads `../sources/ai-governance-framework` at the pinned SHA and writes `data/aigf-snapshot.json`, which records the source SHA. Add `data/README.md` and the NOTICE attribution.
3. **CALM reader** plus the synthetic fixture and tests.
4. **Coverage engine** (D3) plus tests, including the expected Steel Thread results above.
5. **Workbook export** (openpyxl) and the `export` / `check` CLI.
6. **Demo run** against `../sources/ai-steel-thread-demo`; save the output under `out/`, which is git-ignored.
7. **CI workflow:** clone the Steel Thread at the pinned SHA, run tests and `check` (expected to fail on ri-17 and ri-19; decide whether the demo job is allowed to fail).
8. **README:** fill in the Installation, Usage and Development setup TODOs. Final submission is due Wed 2026-11-18 (target 5 PM PT).
