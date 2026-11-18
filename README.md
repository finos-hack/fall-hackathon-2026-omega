# Governance-as-Code Evidence Workbook

[![governance-check](https://github.com/jiaxingxue/gac-evidence-workbook/actions/workflows/governance-check.yml/badge.svg)](https://github.com/jiaxingxue/gac-evidence-workbook/actions/workflows/governance-check.yml)

**Hackathon Track:** 2 – Extend & Utilize FINOS Governance-as-Code

A CLI that reads a FINOS CALM architecture (from the Governance-as-Code Steel Thread), maps its controls to FINOS AI Governance Framework (AIGF) risks and mitigations, flags uncovered risks, and exports an auditor-ready Excel evidence workbook, with a CI check that fails when gaps exist.

> **Status: work in progress.** Built during the FINOS Fall 2026 Hackathon. Features below are planned and may not be implemented yet.

### The problem

Governance-as-Code expresses AI controls as JSON (CALM architectures and control definitions). Auditors and second-line risk teams work in Excel. They can't easily trace a path from an AI risk to the control that addresses it and the evidence that the control is in place when that information lives only in JSON files spread across repositories.

### Planned features

- Read a CALM 1.2 architecture and collect the controls attached to its nodes, relationships and flows, including the AIGF risks and mitigations each control already declares (`aigf-risks`, `aigf-mitigations`). There is no separate hand-written mapping.
- Take the expected risks from the AIGF use case the architecture names (for the Steel Thread, UC-3 Loan Approval).
- Report AIGF risks that no control claims to cover. This is the CI-failing gap check.
- Cross-check claims against AIGF's own `mitigates` links, and warn about unsupported claims and risks that are possibly covered but not claimed.
- Export an Excel workbook that traces risk → mitigation → control → architecture element → evidence (labelled "declared"), with Gaps and Findings sheets.
- Provide a `check` command that exits non-zero when claims-based gaps exist, for use in CI.

Design decisions and data provenance are recorded in [docs/decisions.md](docs/decisions.md) and [docs/data-sources.md](docs/data-sources.md).

## Continuous integration

The [governance-check](.github/workflows/governance-check.yml) workflow has two jobs:

- **tests:** runs the unit tests on Python 3.10 and 3.13 using only the synthetic fixtures in `tests/fixtures/`.
- **steel-thread-check:** clones the [Steel Thread](https://github.com/finos-hack/ai-steel-thread-demo) at the commit pinned in [docs/data-sources.md](docs/data-sources.md), runs `calm validate`, exports the evidence workbook, then runs `gac-workbook check`. The workbook and `summary.md` are uploaded as the `evidence-workbook` artifact even when the check fails.

> **A red `steel-thread-check` is expected.** It means the tool is working: it found real coverage gaps in the Steel Thread architecture. AIGF use case UC-3 (Loan Approval) expects risks ri-17 (Lack of Explainability) and ri-19 (Data Quality and Drift), and no control in the architecture claims either one. The job turns green when those gaps are addressed upstream.

## Installation

> **TODO:** installation instructions will be added once the CLI exists.

## Usage example

> **TODO:** usage examples will be added once the CLI exists.

## Development setup

> **TODO:** development dependencies and test commands will be added once the toolchain is chosen.

## Roadmap

This project was built during a time-boxed FINOS hackathon. List below what you would like to achieve after the hackathon, if the project continues.

1. Expand the CALM control → AIGF mapping beyond the Steel Thread example architecture.
2. Link workbook rows to live evidence sources (CI runs, test reports) instead of static references.

## Contributing

Coding agents should follow [AGENTS.md](./AGENTS.md), which requires a Developer Certificate of Origin sign-off on every commit.

**All commits** must be signed with a DCO signature to avoid being flagged by the DCO Bot. This means that your commit log message must contain a line that looks like the following one, with your actual name and email address:

```
Signed-off-by: John Doe <john.doe@example.com>
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for more information.

## License

Copyright 2026 Jiaxing Xue

Distributed under the [Apache License, Version 2.0](http://www.apache.org/licenses/LICENSE-2.0).

SPDX-License-Identifier: [Apache-2.0](https://spdx.org/licenses/Apache-2.0)
