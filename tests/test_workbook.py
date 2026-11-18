"""Workbook export tests on the synthetic fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from gac_workbook.aigf import load_snapshot
from gac_workbook.calm import load_architecture
from gac_workbook.cli import EXIT_OK, main
from gac_workbook.coverage import compute_coverage
from gac_workbook.workbook import (
    BASIS_ADDITIONAL,
    CHECKLIST_HEADERS,
    FINDINGS_HEADERS,
    SHEETS,
    NO_COVERAGE_TEXT,
    SOURCES_HEADERS,
    TRACEABILITY_HEADERS,
    _row_height,
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
        ("ri-901", "mi-901", "synthetic-leakage-guard", "lending-app", "Claimed & AIGF-supported"),
        ("ri-901", "mi-901", "synthetic-leakage-guard", "lending-app-to-scoring-model", "Claimed & AIGF-supported"),
        ("ri-902", "mi-902", "synthetic-review-loop", "scoring-model", "Claimed – not in AIGF (unsupported)"),
        ("ri-903", "–", NO_COVERAGE_TEXT, "–", "GAP – nothing addresses this risk"),
    ]
    assert all(r.evidence_status == "Declared (not verified)" for r in rows[:3])
    gap = rows[3]
    assert gap.evidence_status == "None"
    assert gap.candidates == "mi-903 (Synthetic draft mitigation (unused)) [Draft]"
    assert all(r.candidates == "" for r in rows[:3])


def test_traceability_column_order_and_gap_row(exported: Path) -> None:
    ws = load_workbook(exported)["Traceability"]
    assert _header(ws) == [
        "Risk ID", "Risk title", "Expected", "Coverage basis", "Control", "Mitigation ID", "Mitigation title",
        "Element type", "Element ID", "Element name", "Requirement URL", "Evidence status",
        "Candidate AIGF mitigations",
    ]
    h = _header(ws)
    gap = next(r for r in _data_rows(ws) if r[h.index("Coverage basis")] == "GAP – nothing addresses this risk")
    assert gap[h.index("Control")] == "No control or mitigation in this architecture addresses this risk"
    assert gap[h.index("Candidate AIGF mitigations")].startswith("mi-903")
    assert int(ws.page_setup.paperSize) == int(ws.PAPERSIZE_LETTER) == 1  # US Letter
    assert ws.page_setup.orientation == "landscape"


def test_catalogue_implied_rows(fixtures: Path) -> None:
    arch = load_architecture(fixtures / "mini.calm.json")
    cat = load_snapshot(fixtures / "mini-aigf.json")
    report = compute_coverage(arch, cat, expected_risks=["ri-901", "ri-904"])
    implied = [(r.risk_id, r.mitigation_id, r.basis) for r in traceability_rows(arch, cat, report)
               if r.basis == "Not claimed – AIGF suggests may cover"]
    assert implied == [("ri-904", "mi-902", "Not claimed – AIGF suggests may cover")]


def test_additional_coverage_for_covered_risk(fixtures: Path, tmp_path: Path) -> None:
    # Make mi-902 (used by synthetic-review-loop, which does not claim ri-901) also mitigate ri-901.
    # ri-901 is already claimed & supported via mi-901, so the mi-902 row is extra context, not amber.
    doc = json.loads((fixtures / "mini-aigf.json").read_text(encoding="utf-8"))
    for m in doc["mitigations"]:
        if m["id"] == "mi-902":
            m["mitigates"] = ["ri-901", "ri-904"]
    aigf = tmp_path / "aigf.json"
    aigf.write_text(json.dumps(doc), encoding="utf-8")
    arch = load_architecture(fixtures / "mini.calm.json")
    cat = load_snapshot(aigf)
    report = compute_coverage(arch, cat, expected_risks=["ri-901", "ri-904"])
    rows = traceability_rows(arch, cat, report)
    by = {(r.risk_id, r.mitigation_id, r.control): r.basis for r in rows}
    assert by[("ri-901", "mi-902", "synthetic-review-loop")] == BASIS_ADDITIONAL
    assert by[("ri-901", "mi-901", "synthetic-leakage-guard")] == "Claimed & AIGF-supported"
    # ri-904 has no supported claim, so it stays amber "Not claimed – AIGF suggests may cover".
    assert by[("ri-904", "mi-902", "synthetic-review-loop")] == "Not claimed – AIGF suggests may cover"
    # No new findings from additional coverage.
    assert {f.finding_type for f in report.findings if f.risk_id == "ri-901"} == set()

    out = tmp_path / "wb.xlsx"
    assert main(["export", "--arch", str(fixtures / "mini.calm.json"), "--aigf", str(aigf), "--out", str(out),
                 "--expected-risks", "ri-901,ri-904"]) == EXIT_OK
    ws = load_workbook(out)["Traceability"]
    h = _header(ws)
    col = h.index("Coverage basis") + 1
    cells = [ws.cell(row=i, column=col) for i in range(2, ws.max_row + 1)]
    fills = {c.value: c.fill.fgColor.rgb[-6:] for c in cells}
    assert fills[BASIS_ADDITIONAL] == "DDEBF7"  # neutral light blue
    assert fills["Not claimed – AIGF suggests may cover"] == "FFEB9C"  # amber


def test_summary_explains_additional_and_sizes_rows(fixtures: Path, tmp_path: Path) -> None:
    out = tmp_path / "wb.xlsx"
    main(["export", "--arch", str(fixtures / "mini.calm.json"), "--aigf", str(fixtures / "mini-aigf.json"),
          "--out", str(out)])
    ws = load_workbook(out)["Summary"]
    texts = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
    assert any(t.startswith(f"'{BASIS_ADDITIONAL}' (light blue)") for t in texts)
    # Coverage-table rows get a height that fits the wrapped status text.
    status_rows = [r for r in range(1, ws.max_row + 1) if str(ws.cell(row=r, column=5).value or "").startswith("GAP")]
    assert status_rows
    for r in status_rows:
        assert ws.row_dimensions[r].height and ws.row_dimensions[r].height >= 30


def test_row_height_estimate() -> None:
    assert _row_height([("short", 22)]) == 18
    # "GAP – not claimed (AIGF suggests mi-4 may cover)" is 49 chars: 3 lines in a 22-wide column.
    assert _row_height([("GAP – not claimed (AIGF suggests mi-4 may cover)", 22)]) == 48


def test_summary_sheet_status_and_facts(exported: Path) -> None:
    ws = load_workbook(exported)["Summary"]
    facts = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)}
    assert facts["Coverage result"] == "GAPS FOUND (1 error, 1 warning)"
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
    assert "**Coverage result: GAPS FOUND (1 error, 1 warning)**" in md
    assert "| ri-903 |" in md
    assert "Recommended action" in md


def test_evidence_required_summary() -> None:
    text = evidence_required({
        "control-id": "mi-901", "name": "X", "aigf-catalog-url": "https://example.invalid",
        "description": "Do the thing.", "tls-required": True, "hosts": ["a", "b"],
    })
    assert text == "Do the thing.\nDeclared parameters: tls-required: true; hosts: a, b"
    assert evidence_required({}) == "(no requirement config declared)"
