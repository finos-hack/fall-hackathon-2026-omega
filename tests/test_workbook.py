"""Workbook export tests on the synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from gac_workbook.aigf import load_snapshot
from gac_workbook.calm import load_architecture
from gac_workbook.cli import EXIT_OK, main
from gac_workbook.coverage import compute_coverage
from gac_workbook.workbook import (
    CHECKLIST_HEADERS,
    FINDINGS_HEADERS,
    SHEETS,
    SOURCES_HEADERS,
    TRACEABILITY_HEADERS,
    evidence_required,
    traceability_rows,
)


@pytest.fixture
def exported(fixtures: Path, tmp_path: Path) -> Path:
    out = tmp_path / "out" / "evidence-workbook.xlsx"
    code = main(["export", "--arch", str(fixtures / "mini.calm.json"), "--aigf", str(fixtures / "mini-aigf.json"),
                 "--out", str(out)])
    assert code == EXIT_OK  # export succeeds even though the fixture has a GAP
    return out


def _header(ws) -> list[str]:
    return [c.value for c in ws[1]]


def _data_rows(ws) -> list[tuple]:
    return [r for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]


def test_sheet_names(exported: Path) -> None:
    assert load_workbook(exported).sheetnames == SHEETS == [
        "Summary", "Traceability", "Findings", "Evidence Checklist", "Sources"
    ]


def test_headers(exported: Path) -> None:
    wb = load_workbook(exported)
    assert _header(wb["Traceability"]) == TRACEABILITY_HEADERS
    assert _header(wb["Findings"]) == FINDINGS_HEADERS
    assert _header(wb["Evidence Checklist"]) == CHECKLIST_HEADERS
    assert _header(wb["Sources"]) == SOURCES_HEADERS
    for name in ("Traceability", "Findings", "Evidence Checklist", "Sources"):
        ws = wb[name]
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref and ws.auto_filter.ref.startswith("A1:")
        assert ws["A1"].font.bold


def test_row_counts(exported: Path) -> None:
    wb = load_workbook(exported)
    # leakage-guard on 2 elements ("both") + review-loop on 1 ("claimed") + ri-903 gap row.
    assert len(_data_rows(wb["Traceability"])) == 4
    # GAP ri-903, UNSUPPORTED CLAIM ri-902, DRAFT REFERENCE uc-901.
    assert len(_data_rows(wb["Findings"])) == 3
    # One row per control use (3 in the fixture).
    assert len(_data_rows(wb["Evidence Checklist"])) == 3
    assert len(_data_rows(wb["Sources"])) == 4


def test_traceability_basis(fixtures: Path) -> None:
    arch = load_architecture(fixtures / "mini.calm.json")
    cat = load_snapshot(fixtures / "mini-aigf.json")
    rows = traceability_rows(arch, cat, compute_coverage(arch, cat))
    assert [(r.risk_id, r.mitigation_id, r.control, r.element_id, r.basis) for r in rows] == [
        ("ri-901", "mi-901", "synthetic-leakage-guard", "lending-app", "both"),
        ("ri-901", "mi-901", "synthetic-leakage-guard", "lending-app-to-scoring-model", "both"),
        ("ri-902", "mi-902", "synthetic-review-loop", "scoring-model", "claimed"),
        ("ri-903", "", "", "", "none (GAP)"),
    ]
    assert all(r.evidence_status == "Declared (not verified)" for r in rows if r.control)


def test_catalogue_implied_rows(fixtures: Path) -> None:
    arch = load_architecture(fixtures / "mini.calm.json")
    cat = load_snapshot(fixtures / "mini-aigf.json")
    report = compute_coverage(arch, cat, expected_risks=["ri-901", "ri-904"])
    implied = [(r.risk_id, r.mitigation_id, r.basis) for r in traceability_rows(arch, cat, report)
               if r.basis == "catalogue-implied"]
    assert implied == [("ri-904", "mi-902", "catalogue-implied")]


def test_summary_sheet_status_and_facts(exported: Path) -> None:
    ws = load_workbook(exported)["Summary"]
    facts = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)}
    assert facts["Overall status"] == "FAIL"
    assert facts["Expected risks"] == 3
    assert facts["Expected risks claimed by a control"] == 2
    assert facts["Claims-based gaps (errors)"] == 1
    assert facts["Findings: warnings"] == 1
    assert facts["AIGF snapshot commit"] == "0" * 40
    assert facts["Tool version"].startswith("gac-workbook ")
    assert facts["Generated at (UTC)"].endswith("Z")


def test_findings_auditor_columns_blank_with_status_dropdown(exported: Path) -> None:
    ws = load_workbook(exported)["Findings"]
    h = _header(ws)
    for row in _data_rows(ws):
        for col in ("Owner", "Action", "Due date", "Status"):
            assert row[h.index(col)] is None
        assert row[h.index("Recommended action")]
    assert [row[h.index("Severity")] for row in _data_rows(ws)] == ["ERROR", "WARNING", "INFO"]


def test_checklist_result_dropdown(exported: Path) -> None:
    ws = load_workbook(exported)["Evidence Checklist"]
    lists = [dv.formula1 for dv in ws.data_validations.dataValidation]
    assert '"Pass,Fail,N/A"' in lists
    h = _header(ws)
    for row in _data_rows(ws):
        assert row[h.index("Evidence status")] == "Declared (not verified)"
        assert row[h.index("Result")] is None


def test_sources_attribution(exported: Path) -> None:
    ws = load_workbook(exported)["Sources"]
    text = " ".join(str(v) for r in ws.iter_rows(values_only=True) for v in r if v)
    assert "creativecommons.org/licenses/by/4.0" in text


def test_summary_markdown_written(exported: Path) -> None:
    md = (exported.parent / "summary.md").read_text(encoding="utf-8")
    assert "**Overall status: FAIL**" in md
    assert "| ri-903 |" in md
    assert "Recommended action" in md


def test_evidence_required_summary() -> None:
    text = evidence_required({
        "control-id": "mi-901", "name": "X", "aigf-catalog-url": "https://example.invalid",
        "description": "Do the thing.", "tls-required": True, "hosts": ["a", "b"],
    })
    assert text == "Do the thing.\nDeclared parameters: tls-required: true; hosts: a, b"
    assert evidence_required({}) == "(no requirement config declared)"
