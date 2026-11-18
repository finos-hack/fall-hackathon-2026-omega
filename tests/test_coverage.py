"""Coverage engine tests on the synthetic fixtures only (tests/fixtures/README.md)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from gac_workbook.aigf import load_snapshot
from gac_workbook.calm import load_architecture, parse_architecture
from gac_workbook.coverage import (
    DRAFT_REFERENCE,
    ERROR,
    GAP,
    INFO,
    POSSIBLY_COVERED,
    UNKNOWN_ID,
    UNSUPPORTED_CLAIM,
    WARNING,
    CoverageError,
    compute_coverage,
)


@pytest.fixture
def cat(fixtures: Path):
    return load_snapshot(fixtures / "mini-aigf.json")


@pytest.fixture
def arch_doc(fixtures: Path) -> dict:
    return json.loads((fixtures / "mini.calm.json").read_text(encoding="utf-8"))


def _of(report, finding_type):
    return [f for f in report.findings if f.finding_type == finding_type]


def test_expected_claimed_and_implied_views(fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat)
    assert r.expected_risks == ["ri-901", "ri-902", "ri-903"]
    assert r.expected_source == "AIGF use case uc-901_synthetic-lending related_risks"
    status = {row.risk_id: row.status for row in r.risks}
    assert status == {"ri-901": "covered", "ri-902": "covered (unsupported claim only)", "ri-903": "GAP"}
    assert r.claims_gaps == ["ri-903"]
    assert r.catalogue_implied_gaps == ["ri-902", "ri-903"]


def test_gap_finding(fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat)
    (gap,) = _of(r, GAP)
    assert (gap.severity, gap.risk_id) == (ERROR, "ri-903")
    assert "no control" in gap.message and "ri-903 (Synthetic risk: unexplained decisions)" in gap.message
    assert gap.recommended_action == (
        "Add or identify a control that addresses ri-903 (Synthetic risk: unexplained decisions), "
        "or document a risk-acceptance rationale."
    )
    assert r.has_errors


def test_every_finding_has_a_recommended_action(arch_doc: dict, cat) -> None:
    doc = copy.deepcopy(arch_doc)
    doc["nodes"][2]["controls"]["synthetic-review-loop"]["aigf-mitigations"] = ["mi-902", "mi-903", "mi-999"]
    r = compute_coverage(parse_architecture(doc), cat, expected_risks=["ri-901", "ri-902", "ri-903", "ri-904"])
    assert {f.finding_type for f in r.findings} == {GAP, UNSUPPORTED_CLAIM, POSSIBLY_COVERED, UNKNOWN_ID, DRAFT_REFERENCE}
    assert all(f.recommended_action for f in r.findings)


def test_unsupported_claim_finding(fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat)
    (f,) = _of(r, UNSUPPORTED_CLAIM)
    assert (f.severity, f.control_key, f.mitigation_id, f.risk_id) == (
        WARNING,
        "synthetic-review-loop",
        "mi-902",
        "ri-902",
    )
    assert f.elements == ("node:scoring-model",)
    assert f.recommended_action == (
        "Confirm the rationale for this mapping with the control owner, or remove the claim. "
        "The AIGF catalogue doesn't list this risk for this mitigation."
    )
    # The well-supported claim (mi-901 -> ri-901) produces no finding.
    assert not [x for x in r.findings if x.control_key == "synthetic-leakage-guard"]


def test_possibly_covered_not_claimed_finding(fixtures: Path, cat) -> None:
    # ri-904 is in mi-902's `mitigates` (mi-902 is used), but no control claims ri-904.
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat, expected_risks=["ri-901", "ri-904"])
    (f,) = _of(r, POSSIBLY_COVERED)
    assert (f.severity, f.risk_id, f.mitigation_id) == (WARNING, "ri-904", "mi-902")
    assert f.recommended_action == "Confirm and add ri-904 to that control's aigf-risks, or record why it does not apply."
    assert [g.risk_id for g in _of(r, GAP)] == ["ri-904"]  # it is still a claims-based gap
    assert {row.risk_id: row.status for row in r.risks}["ri-904"] == "GAP (possibly covered)"


def test_unknown_id_in_control(arch_doc: dict, cat) -> None:
    doc = copy.deepcopy(arch_doc)
    ctrl = doc["nodes"][1]["controls"]["synthetic-leakage-guard"]
    ctrl["aigf-mitigations"] = ["mi-901", "mi-999"]
    ctrl["aigf-risks"] = ["ri-901", "ri-998"]
    r = compute_coverage(parse_architecture(doc), cat)
    unknown = {f.mitigation_id or f.risk_id for f in _of(r, UNKNOWN_ID)}
    assert unknown == {"mi-999", "ri-998"}
    assert all(f.severity == ERROR for f in _of(r, UNKNOWN_ID))
    assert all(f.recommended_action == "Correct the ID or update the AIGF snapshot." for f in _of(r, UNKNOWN_ID))


def test_unknown_id_in_override_and_use_case(arch_doc: dict, fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat, expected_risks=["ri-901", "ri-999"])
    (f,) = _of(r, UNKNOWN_ID)
    assert f.risk_id == "ri-999" and "--expected-risks" in f.message
    assert not [g for g in _of(r, GAP) if g.risk_id == "ri-999"]  # reported once, as unknown

    doc = copy.deepcopy(arch_doc)
    doc["metadata"][0]["finos-use-case"] = "uc-999_nope"
    r2 = compute_coverage(parse_architecture(doc), cat)
    assert [f.message.split(" is ")[0] for f in _of(r2, UNKNOWN_ID)] == ["Use case uc-999_nope"]
    assert r2.expected_risks == [] and r2.has_errors


def test_draft_reference_use_case(fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat)
    drafts = _of(r, DRAFT_REFERENCE)
    assert len(drafts) == 1
    assert drafts[0].severity == INFO
    assert "uc-901_synthetic-lending" in drafts[0].message and "Draft" in drafts[0].message
    assert drafts[0].recommended_action == "Re-run the check when the AIGF item leaves Draft."


def test_draft_reference_control(arch_doc: dict, cat) -> None:
    doc = copy.deepcopy(arch_doc)
    doc["nodes"][2]["controls"]["synthetic-review-loop"]["aigf-mitigations"] = ["mi-902", "mi-903"]
    r = compute_coverage(parse_architecture(doc), cat)
    control_drafts = [f for f in _of(r, DRAFT_REFERENCE) if f.control_key]
    assert [(f.control_key, f.mitigation_id, f.severity) for f in control_drafts] == [
        ("synthetic-review-loop", "mi-903", INFO)
    ]


def test_no_use_case_and_no_override_is_an_input_error(arch_doc: dict, cat) -> None:
    doc = copy.deepcopy(arch_doc)
    del doc["metadata"]
    with pytest.raises(CoverageError):
        compute_coverage(parse_architecture(doc), cat)
    # With an override it works.
    r = compute_coverage(parse_architecture(doc), cat, expected_risks=["ri-901"])
    assert not r.has_errors


def test_findings_are_ordered_by_severity(fixtures: Path, cat) -> None:
    r = compute_coverage(load_architecture(fixtures / "mini.calm.json"), cat)
    sev = [f.severity for f in r.findings]
    assert sev == sorted(sev, key={ERROR: 0, WARNING: 1, INFO: 2}.get)
