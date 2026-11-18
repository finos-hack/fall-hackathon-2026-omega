"""FINOS AI Governance Framework (AIGF) catalogue: front-matter parsing and snapshot loading.

The snapshot keeps identifiers, titles, status, links and catalogue URLs only, never body text.
AIGF content is (c) FINOS, licensed under CC-BY-4.0.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

AIGF_REPO_URL = "https://github.com/finos/ai-governance-framework"
AIGF_LICENSE = "CC-BY-4.0"
AIGF_ATTRIBUTION = "© FINOS, CC-BY-4.0"
# From docs/CNAME in the AIGF repository.
CATALOGUE_SITE = "https://air-governance-framework.finos.org"

# Catalogue page URLs follow the Jekyll config in the AIGF repo (docs/_config.yml):
# risks and mitigations use Jekyll's default collection permalink /:collection/:path.html,
# use cases set `permalink: /usecase/:name/`. The mitigation pattern matches the
# `aigf-catalog-url` values used in the Steel Thread architecture.
COLLECTIONS = {
    # kind: (directory, filename prefix, URL builder)
    "risk": ("_risks", "ri", lambda stem: f"{CATALOGUE_SITE}/risks/{stem}.html"),
    "mitigation": ("_mitigations", "mi", lambda stem: f"{CATALOGUE_SITE}/mitigations/{stem}.html"),
    "use_case": ("_usecases", "uc", lambda stem: f"{CATALOGUE_SITE}/usecase/{stem}/"),
}

DRAFT_STATUS = "Draft"

_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_STEM_RE = re.compile(r"^(?P<prefix>ri|mi|uc)-(?P<num>\d+)_[A-Za-z0-9._-]+$")


class FrontMatterError(ValueError):
    """Raised when front matter cannot be parsed safely."""


def parse_front_matter(text: str) -> tuple[dict[str, Any], list[str]] | None:
    """Parse the YAML front matter at the top of a Markdown file.

    Returns ``(data, duplicate_keys)`` or ``None`` when the file has no front matter.

    Duplicate top-level keys are handled explicitly instead of relying on PyYAML's
    silent last-one-wins behaviour: when every occurrence is a list or empty, the
    values are merged in order without repeats. Any other duplicate raises
    ``FrontMatterError``. (At the pinned AIGF commit, ri-2 and ri-17 both declare
    ``related_risks`` twice, first empty and then populated.)
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return None
    loader = yaml.SafeLoader(match.group(1))
    try:
        node = loader.get_single_node()
        if node is None:
            return {}, []
        if not isinstance(node, yaml.MappingNode):
            raise FrontMatterError("front matter is not a mapping")
        data: dict[str, Any] = {}
        duplicates: list[str] = []
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=True)
            value = loader.construct_object(value_node, deep=True)
            if key in data:
                duplicates.append(key)
                data[key] = _merge_duplicate(key, data[key], value)
            else:
                data[key] = value
        return data, duplicates
    except yaml.YAMLError as exc:
        raise FrontMatterError(str(exc)) from exc
    finally:
        loader.dispose()


def _merge_duplicate(key: str, first: Any, second: Any) -> list[Any]:
    if not all(v is None or isinstance(v, list) for v in (first, second)):
        raise FrontMatterError(f"duplicate key {key!r} with non-list values")
    merged: list[Any] = []
    for item in (first or []) + (second or []):
        if item not in merged:
            merged.append(item)
    return merged


def _as_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def build_snapshot(aigf_root: Path, *, commit: str, generated_at: str) -> dict[str, Any]:
    """Build the snapshot dictionary from an AIGF checkout at ``aigf_root``."""
    docs = Path(aigf_root) / "docs"
    if not docs.is_dir():
        raise FileNotFoundError(f"no docs/ directory under {aigf_root}")

    notes: list[str] = []
    out: dict[str, list[dict[str, Any]]] = {"risks": [], "mitigations": [], "use_cases": []}
    out_key = {"risk": "risks", "mitigation": "mitigations", "use_case": "use_cases"}

    for kind, (subdir, prefix, url_for) in COLLECTIONS.items():
        directory = docs / subdir
        if not directory.is_dir():
            raise FileNotFoundError(f"missing AIGF collection directory {directory}")
        for path in sorted(directory.glob(f"{prefix}-*.md")):
            stem = path.stem
            rel = f"docs/{subdir}/{path.name}"
            m = _STEM_RE.match(stem)
            parsed = parse_front_matter(path.read_text(encoding="utf-8"))
            if parsed is None or m is None:
                notes.append(f"{rel}: skipped (no front matter or not an {prefix}-N_ file)")
                continue
            data, dups = parsed
            for key in dups:
                notes.append(f"{rel}: duplicate key {key!r} merged -> {data[key]!r}")
            short_id = f"{prefix}-{int(m.group('num'))}"
            seq = data.get("sequence")
            if seq is not None and int(seq) != int(m.group("num")):
                notes.append(f"{rel}: sequence {seq} differs from filename number {m.group('num')}")
            status = data.get("doc-status")
            entry: dict[str, Any] = {
                "id": stem if kind == "use_case" else short_id,
                "title": data.get("title"),
                "doc_status": status,
                "draft": status == DRAFT_STATUS,
                "url": url_for(stem),
                "source_file": rel,
            }
            if kind == "mitigation":
                entry["mitigates"] = _as_id_list(data.get("mitigates"))
            if kind == "use_case":
                entry["short_id"] = short_id
                entry["related_risks"] = _as_id_list(data.get("related_risks"))
            out[out_key[kind]].append(entry)

    for items in out.values():
        items.sort(key=lambda e: int(_STEM_RE.match(Path(e["source_file"]).stem).group("num")))

    return {
        "source": {
            "repo": AIGF_REPO_URL,
            "commit": commit,
            "license": AIGF_LICENSE,
            "attribution": AIGF_ATTRIBUTION,
            "catalogue_site": CATALOGUE_SITE + "/",
        },
        "generated_at": generated_at,
        "generator": "scripts/build_aigf_snapshot.py",
        "content_note": "IDs, titles, status, links and catalogue URLs only; no body text.",
        "parse_notes": notes,
        "risks": out["risks"],
        "mitigations": out["mitigations"],
        "use_cases": out["use_cases"],
    }


@dataclass(frozen=True)
class Catalogue:
    """In-memory view of an AIGF snapshot, keyed by ID."""

    source: dict[str, Any]
    risks: dict[str, dict[str, Any]] = field(default_factory=dict)
    mitigations: dict[str, dict[str, Any]] = field(default_factory=dict)
    use_cases: dict[str, dict[str, Any]] = field(default_factory=dict)

    def use_case(self, use_case_id: str) -> dict[str, Any]:
        """Look up a use case by full ID (``uc-3_loan-approval``) or short ID (``uc-3``)."""
        if use_case_id in self.use_cases:
            return self.use_cases[use_case_id]
        for uc in self.use_cases.values():
            if uc.get("short_id") == use_case_id:
                return uc
        raise KeyError(f"use case {use_case_id!r} not in AIGF snapshot")


def load_snapshot(path: Path | str) -> Catalogue:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return Catalogue(
        source=data["source"],
        risks={r["id"]: r for r in data["risks"]},
        mitigations={m["id"]: m for m in data["mitigations"]},
        use_cases={u["id"]: u for u in data["use_cases"]},
    )
