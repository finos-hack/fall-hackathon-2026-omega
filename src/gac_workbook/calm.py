"""Load a FINOS CALM 1.2 architecture and list every use of a control.

Each control in CALM is an object keyed by control name under ``controls`` on a node,
relationship or flow. Each control has ``description``, ``aigf-mitigations``,
``aigf-risks`` and ``requirements[]`` (each with a ``requirement-url`` and an inline
``config``). One ``ControlUse`` row is produced per (element, control, requirement).

The evidence is what the architecture *declares*. Nothing here checks runtime behaviour.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

EVIDENCE_DECLARED = "declared"

# CALM top-level arrays and the element type each holds.
_ELEMENT_ARRAYS = (("nodes", "node"), ("relationships", "relationship"), ("flows", "flow"))


@dataclass(frozen=True)
class ControlUse:
    element_type: str  # "node" | "relationship" | "flow"
    element_id: str
    element_name: str | None  # CALM relationships usually have no name
    control_key: str
    description: str | None
    aigf_mitigations: tuple[str, ...]
    aigf_risks: tuple[str, ...]
    requirement_url: str | None
    config: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)
    evidence_status: str = EVIDENCE_DECLARED


@dataclass(frozen=True)
class Architecture:
    path: str
    schema: str | None
    unique_id: str | None
    name: str | None
    use_case_id: str | None  # from metadata `finos-use-case`
    metadata_mitigations: tuple[str, ...]
    metadata_risks: tuple[str, ...]
    control_uses: tuple[ControlUse, ...]

    def control_keys(self) -> list[str]:
        return sorted({cu.control_key for cu in self.control_uses})

    def elements_with_controls(self, element_type: str) -> list[str]:
        return sorted({cu.element_id for cu in self.control_uses if cu.element_type == element_type})


class CalmError(ValueError):
    """Raised when a file is not a usable CALM architecture."""


def _id_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _metadata_entries(metadata: Any) -> Iterable[dict[str, Any]]:
    # CALM allows metadata as a single object or an array of objects.
    if isinstance(metadata, dict):
        yield metadata
    elif isinstance(metadata, list):
        for entry in metadata:
            if isinstance(entry, dict):
                yield entry


def _first_meta(metadata: Any, key: str) -> Any:
    for entry in _metadata_entries(metadata):
        if key in entry:
            return entry[key]
    return None


def _control_uses(element_type: str, element: dict[str, Any]) -> list[ControlUse]:
    controls = element.get("controls") or {}
    if not isinstance(controls, dict):
        raise CalmError(f"{element_type} {element.get('unique-id')!r}: `controls` must be an object")
    rows: list[ControlUse] = []
    for key, control in controls.items():
        common = dict(
            element_type=element_type,
            element_id=element.get("unique-id"),
            element_name=element.get("name"),
            control_key=key,
            description=control.get("description"),
            aigf_mitigations=_id_tuple(control.get("aigf-mitigations")),
            aigf_risks=_id_tuple(control.get("aigf-risks")),
        )
        requirements = control.get("requirements") or []
        if not requirements:
            rows.append(ControlUse(requirement_url=None, config={}, **common))
        for req in requirements:
            rows.append(
                ControlUse(
                    requirement_url=req.get("requirement-url"),
                    config=dict(req.get("config") or {}),
                    **common,
                )
            )
    return rows


def parse_architecture(doc: dict[str, Any], path: str = "<memory>") -> Architecture:
    if not isinstance(doc, dict) or "nodes" not in doc:
        raise CalmError(f"{path}: not a CALM architecture (no `nodes`)")
    uses: list[ControlUse] = []
    for array_key, element_type in _ELEMENT_ARRAYS:
        for element in doc.get(array_key) or []:
            uses.extend(_control_uses(element_type, element))
    metadata = doc.get("metadata")
    return Architecture(
        path=path,
        schema=doc.get("$schema"),
        unique_id=doc.get("unique-id"),
        name=doc.get("name"),
        use_case_id=_first_meta(metadata, "finos-use-case"),
        metadata_mitigations=_id_tuple(_first_meta(metadata, "aigf-mitigations")),
        metadata_risks=_id_tuple(_first_meta(metadata, "aigf-risks")),
        control_uses=tuple(uses),
    )


def load_architecture(path: Path | str) -> Architecture:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return parse_architecture(doc, path=str(path))
