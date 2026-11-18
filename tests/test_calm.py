from __future__ import annotations

import json
from pathlib import Path

import pytest

from gac_workbook.calm import EVIDENCE_DECLARED, CalmError, load_architecture, parse_architecture


def test_mini_fixture_rows(fixtures: Path) -> None:
    arch = load_architecture(fixtures / "mini.calm.json")

    assert arch.schema == "https://calm.finos.org/release/1.2/meta/calm.json"
    assert arch.use_case_id == "uc-901_synthetic-lending"
    assert arch.metadata_mitigations == ("mi-901", "mi-902")
    assert arch.metadata_risks == ("ri-901",)

    assert len(arch.control_uses) == 3
    assert arch.control_keys() == ["synthetic-leakage-guard", "synthetic-review-loop"]
    assert arch.elements_with_controls("node") == ["lending-app", "scoring-model"]
    assert arch.elements_with_controls("relationship") == ["lending-app-to-scoring-model"]
    assert arch.elements_with_controls("flow") == []


def test_mini_fixture_row_contents(fixtures: Path) -> None:
    arch = load_architecture(fixtures / "mini.calm.json")
    by_elem = {(cu.element_type, cu.element_id): cu for cu in arch.control_uses}

    node_row = by_elem[("node", "scoring-model")]
    assert node_row.element_name == "Scoring Model"
    assert node_row.control_key == "synthetic-review-loop"
    assert node_row.aigf_mitigations == ("mi-902",)
    assert node_row.aigf_risks == ("ri-902",)
    assert node_row.requirement_url == "https://example.invalid/control-requirement/mi-902-review-loop"
    assert node_row.config == {"control-id": "mi-902", "name": "Synthetic review loop"}
    assert node_row.evidence_status == EVIDENCE_DECLARED == "declared"
    assert node_row.description.startswith("Unsupported claim")

    rel_row = by_elem[("relationship", "lending-app-to-scoring-model")]
    assert rel_row.element_name is None  # CALM relationships carry no name
    assert rel_row.config["scope"] == "edge"


def _minimal(**extra) -> dict:
    doc = {"$schema": "https://calm.finos.org/release/1.2/meta/calm.json", "nodes": []}
    doc.update(extra)
    return doc


def test_flow_controls_and_multiple_requirements() -> None:
    control = {
        "description": "two requirements",
        "aigf-mitigations": ["mi-901"],
        "aigf-risks": ["ri-901", "ri-902"],
        "requirements": [
            {"requirement-url": "https://example.invalid/a", "config": {"control-id": "mi-901"}},
            {"requirement-url": "https://example.invalid/b"},
        ],
    }
    doc = _minimal(flows=[{"unique-id": "f1", "name": "Flow One", "transitions": [], "controls": {"c": control}}])
    arch = parse_architecture(doc)
    assert [(cu.element_type, cu.element_id, cu.requirement_url) for cu in arch.control_uses] == [
        ("flow", "f1", "https://example.invalid/a"),
        ("flow", "f1", "https://example.invalid/b"),
    ]
    assert arch.control_uses[1].config == {}
    assert arch.control_uses[0].aigf_risks == ("ri-901", "ri-902")


def test_control_without_requirements_still_listed() -> None:
    doc = _minimal(nodes=[{"unique-id": "n1", "name": "N", "controls": {"c": {"aigf-risks": ["ri-901"]}}}])
    (cu,) = parse_architecture(doc).control_uses
    assert cu.requirement_url is None
    assert cu.aigf_mitigations == ()
    assert cu.aigf_risks == ("ri-901",)


def test_metadata_as_object() -> None:
    arch = parse_architecture(_minimal(metadata={"finos-use-case": "uc-901_synthetic-lending"}))
    assert arch.use_case_id == "uc-901_synthetic-lending"


def test_missing_metadata_gives_no_use_case() -> None:
    arch = parse_architecture(_minimal())
    assert arch.use_case_id is None
    assert arch.control_uses == ()


def test_not_calm_raises(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with pytest.raises(CalmError):
        load_architecture(p)
