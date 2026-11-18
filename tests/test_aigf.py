from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from conftest import PINNED_AIGF_COMMIT, REPO_ROOT
from gac_workbook.aigf import FrontMatterError, build_snapshot, load_snapshot, parse_front_matter

BODY_MARKER = "BODY TEXT MUST NOT APPEAR IN SNAPSHOT"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tiny_aigf(tmp_path: Path) -> Path:
    """A tiny AIGF-shaped docs tree (synthetic; mirrors the real front-matter layout)."""
    docs = tmp_path / "docs"
    _write(
        docs / "_risks" / "ri-1_first-risk.md",
        "---\nsequence: 1\ntitle: First Risk\nlayout: risk\ndoc-status: Approved-Specification\n"
        "type: SEC\nrelated_risks:\n  - ri-10  # comment\n---\n\n" + BODY_MARKER + "\n",
    )
    # Same pattern as ri-17 / ri-2 upstream: the key appears twice, empty first.
    _write(
        docs / "_risks" / "ri-10_dup-risk.md",
        "---\nsequence: 10\ntitle: Dup Risk\nlayout: risk\ndoc-status: Draft\nrelated_risks:\n"
        "other_references:\n  - x-1\nrelated_risks:\n  - ri-1\n---\n" + BODY_MARKER + "\n",
    )
    _write(
        docs / "_mitigations" / "mi-2_some-mitigation.md",
        "---\nsequence: 2\ntitle: Some Mitigation\nlayout: mitigation\ndoc-status: Approved-Specification\n"
        "type: PREV\nmitigates:\n  - ri-1   # First Risk\n  - ri-10\nrelated_mitigations:\n---\n"
        + BODY_MARKER + "\n",
    )
    _write(
        docs / "_usecases" / "uc-1_tiny-case.md",
        '---\nsequence: 1\ntitle: "Tiny Case"\nlayout: usecase\ndoc-status: Draft\n'
        "related_risks:\n  - ri-1\n  - ri-10\n---\n" + BODY_MARKER + "\n",
    )
    _write(docs / "_usecases" / "uc-index.md", "# Index page without front matter\n")
    return tmp_path


def test_build_snapshot_tiny_tree(tiny_aigf: Path) -> None:
    snap = build_snapshot(tiny_aigf, commit="abc123", generated_at="2026-11-18T00:00:00Z")

    assert snap["source"]["commit"] == "abc123"
    assert snap["source"]["license"] == "CC-BY-4.0"
    assert snap["source"]["attribution"] == "© FINOS, CC-BY-4.0"
    assert snap["generated_at"] == "2026-11-18T00:00:00Z"

    # Numeric ordering, not lexical (ri-1 before ri-10).
    assert [r["id"] for r in snap["risks"]] == ["ri-1", "ri-10"]
    assert snap["risks"][0] == {
        "id": "ri-1",
        "title": "First Risk",
        "doc_status": "Approved-Specification",
        "draft": False,
        "url": "https://air-governance-framework.finos.org/risks/ri-1_first-risk.html",
        "source_file": "docs/_risks/ri-1_first-risk.md",
    }
    assert snap["risks"][1]["draft"] is True

    (mi,) = snap["mitigations"]
    assert mi["id"] == "mi-2"
    assert mi["mitigates"] == ["ri-1", "ri-10"]
    assert mi["url"] == "https://air-governance-framework.finos.org/mitigations/mi-2_some-mitigation.html"

    (uc,) = snap["use_cases"]
    assert uc["id"] == "uc-1_tiny-case"
    assert uc["short_id"] == "uc-1"
    assert uc["title"] == "Tiny Case"
    assert uc["related_risks"] == ["ri-1", "ri-10"]
    assert uc["url"] == "https://air-governance-framework.finos.org/usecase/uc-1_tiny-case/"
    assert uc["draft"] is True

    notes = "\n".join(snap["parse_notes"])
    assert "ri-10_dup-risk.md: duplicate key 'related_risks'" in notes
    assert "uc-index.md: skipped" in notes


def test_snapshot_contains_no_body_text(tiny_aigf: Path) -> None:
    snap = build_snapshot(tiny_aigf, commit="abc123", generated_at="x")
    assert BODY_MARKER not in json.dumps(snap)


def test_duplicate_key_merge_empty_then_list() -> None:
    data, dups = parse_front_matter("---\nrelated_risks:\nx: 1\nrelated_risks:\n  - ri-22\n  - ri-16\n---\n")
    assert dups == ["related_risks"]
    assert data["related_risks"] == ["ri-22", "ri-16"]


def test_duplicate_key_merge_two_lists_keeps_order_without_repeats() -> None:
    data, _ = parse_front_matter("---\nk:\n  - a\n  - b\nk:\n  - b\n  - c\n---\n")
    assert data["k"] == ["a", "b", "c"]


def test_duplicate_scalar_key_is_rejected() -> None:
    with pytest.raises(FrontMatterError):
        parse_front_matter("---\ntitle: A\ntitle: B\n---\n")


def test_no_front_matter_returns_none() -> None:
    assert parse_front_matter("# Just markdown\n") is None


def test_ri17_duplicate_key_real_file(real_aigf_root: Path) -> None:
    """What actually happens with ri-17 at the pinned commit (measured, not assumed)."""
    path = next((real_aigf_root / "docs" / "_risks").glob("ri-17_*.md"))
    text = path.read_text(encoding="utf-8")
    front = text.split("---", 2)[1]

    # The key really is declared twice ...
    node = yaml.compose(front)
    assert [k.value for k, _ in node.value].count("related_risks") == 2
    # ... PyYAML's safe_load silently keeps the last occurrence ...
    assert yaml.safe_load(front)["related_risks"] == ["ri-22", "ri-16", "ri-18"]
    # ... and our loader merges explicitly (the first occurrence is empty) and reports it.
    data, dups = parse_front_matter(text)
    assert dups == ["related_risks"]
    assert data["related_risks"] == ["ri-22", "ri-16", "ri-18"]


def test_committed_snapshot_matches_pinned_source() -> None:
    cat = load_snapshot(REPO_ROOT / "data" / "aigf-snapshot.json")
    assert cat.source["commit"] == PINNED_AIGF_COMMIT
    assert len(cat.risks) == 24
    assert len(cat.mitigations) == 25
    assert {k for k, v in cat.risks.items() if v["draft"]} == {"ri-30"}
    assert {k for k, v in cat.mitigations.items() if v["draft"]} == {"mi-24", "mi-25"}
    assert cat.use_case("uc-3")["related_risks"] == ["ri-1", "ri-4", "ri-6", "ri-14", "ri-17", "ri-19"]
    assert "ri-1" not in cat.mitigations["mi-11"]["mitigates"]  # basis of finding (a) in decisions.md
    assert "ri-19" in cat.mitigations["mi-4"]["mitigates"]  # basis of finding (b)


def test_committed_snapshot_is_reproducible(real_aigf_root: Path) -> None:
    committed = json.loads((REPO_ROOT / "data" / "aigf-snapshot.json").read_text(encoding="utf-8"))
    rebuilt = build_snapshot(
        real_aigf_root, commit=committed["source"]["commit"], generated_at=committed["generated_at"]
    )
    assert rebuilt == committed


def test_load_mini_aigf_fixture(fixtures: Path) -> None:
    cat = load_snapshot(fixtures / "mini-aigf.json")
    assert set(cat.risks) == {"ri-901", "ri-902", "ri-903", "ri-904"}
    assert cat.mitigations["mi-902"]["mitigates"] == ["ri-904"]
    assert cat.use_case("uc-901_synthetic-lending")["related_risks"] == ["ri-901", "ri-902", "ri-903"]
    assert cat.use_case("uc-901")["id"] == "uc-901_synthetic-lending"
    with pytest.raises(KeyError):
        cat.use_case("uc-999")
