# Test fixtures

**Synthetic test fixtures, written for this project's unit tests. They are not derived from the Steel Thread or copied from AIGF.**

All IDs (`ri-90x`, `mi-90x`, `uc-901_synthetic-lending`) and titles are made up, and URLs point to `example.invalid`. Don't use these files as real governance data.

| File | Shape | Purpose |
|---|---|---|
| `mini.calm.json` | CALM 1.2 architecture: 4 nodes, 1 relationship, 1 flow | Exercises the CALM loader and, later, the coverage engine |
| `mini-aigf.json` | Same shape as `data/aigf-snapshot.json` | A tiny catalogue that matches `mini.calm.json` |

Cases built into the pair:

| Case | Where | Expected result |
|---|---|---|
| Well-supported claim | `synthetic-leakage-guard` claims mi-901 → ri-901; `mi-901.mitigates` contains ri-901 | No finding |
| Unsupported claim | `synthetic-review-loop` claims mi-902 → ri-902; `mi-902.mitigates` is only ri-904 | Warning (a) |
| Expected risk with no control | ri-903 is in uc-901's `related_risks`; no control claims it, and no mitigation used in the architecture lists it | Claims-based gap (error) and catalogue-implied gap |
| Draft items | ri-904, mi-903, uc-901 | `draft: true` |

Control uses in `mini.calm.json`: 3 rows. `synthetic-leakage-guard` appears on node `lending-app` and relationship `lending-app-to-scoring-model`, and `synthetic-review-loop` on node `scoring-model`. The flow has no controls.
