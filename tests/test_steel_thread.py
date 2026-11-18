"""Integration checks against the real Steel Thread architecture.

The Steel Thread has no license, so it is never committed here. These tests read a local
clone (../sources/ai-steel-thread-demo or $STEEL_THREAD_ROOT) and are skipped when it's absent.
Expected values come from docs/decisions.md (D3).
"""

from __future__ import annotations

from pathlib import Path

from conftest import REPO_ROOT
from gac_workbook.aigf import load_snapshot
from gac_workbook.calm import load_architecture
from gac_workbook.coverage import GAP, POSSIBLY_COVERED, UNKNOWN_ID, UNSUPPORTED_CLAIM, compute_coverage


def _report(path: Path):
    return compute_coverage(load_architecture(path), load_snapshot(REPO_ROOT / "data" / "aigf-snapshot.json"))


def test_loader_counts(steel_thread_arch: Path) -> None:
    arch = load_architecture(steel_thread_arch)
    assert len(arch.control_keys()) == 4
    assert len(arch.elements_with_controls("node")) == 11
    assert len(arch.elements_with_controls("relationship")) == 2
    assert arch.elements_with_controls("flow") == []


def test_coverage_matches_decisions(steel_thread_arch: Path) -> None:
    r = _report(steel_thread_arch)
    assert r.expected_risks == ["ri-1", "ri-4", "ri-6", "ri-14", "ri-17", "ri-19"]
    assert r.claims_gaps == ["ri-17", "ri-19"]
    assert r.catalogue_implied_gaps == ["ri-17"]
    assert [(f.control_key, f.mitigation_id, f.risk_id) for f in r.findings if f.finding_type == UNSUPPORTED_CLAIM] == [
        ("human-feedback-loop", "mi-11", "ri-1")
    ]
    assert [(f.risk_id, f.mitigation_id) for f in r.findings if f.finding_type == POSSIBLY_COVERED] == [("ri-19", "mi-4")]
    assert [f.risk_id for f in r.findings if f.finding_type == GAP] == ["ri-17", "ri-19"]
    assert not [f for f in r.findings if f.finding_type == UNKNOWN_ID]
    assert r.has_errors
