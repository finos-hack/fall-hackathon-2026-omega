"""Coverage of expected AIGF risks by the controls declared in a CALM architecture.

Three views (see docs/decisions.md, D3):

- expected risks: the related_risks of the AIGF use case the architecture names
  (or an explicit override);
- claimed coverage: risks named in controls' ``aigf-risks``;
- catalogue-implied coverage: risks in AIGF ``mitigates`` of the mitigations controls use.

Findings: GAP (error), UNKNOWN ID (error), UNSUPPORTED CLAIM (warning),
POSSIBLY COVERED, NOT CLAIMED (warning), DRAFT REFERENCE (info).
All evidence is what the architecture declares; nothing is verified at runtime.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .aigf import Catalogue
from .calm import Architecture

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}

GAP = "GAP"
UNSUPPORTED_CLAIM = "UNSUPPORTED CLAIM"
POSSIBLY_COVERED = "POSSIBLY COVERED, NOT CLAIMED"
UNKNOWN_ID = "UNKNOWN ID"
DRAFT_REFERENCE = "DRAFT REFERENCE"

_AIGF_ID_RE = re.compile(r"^(ri|mi)-\d+$")


class CoverageError(ValueError):
    """Raised when coverage cannot be computed (e.g. no expected risks can be determined)."""


@dataclass(frozen=True)
class Finding:
    finding_type: str
    severity: str
    message: str
    risk_id: str | None = None
    mitigation_id: str | None = None
    control_key: str | None = None
    elements: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlSummary:
    control_key: str
    mitigations: tuple[str, ...]
    risks: tuple[str, ...]
    elements: tuple[str, ...]  # "node:<id>", "relationship:<id>", "flow:<id>"


@dataclass(frozen=True)
class RiskRow:
    risk_id: str
    title: str | None
    expected: bool
    claimed_by: tuple[str, ...]  # control keys
    implied_by: tuple[str, ...]  # mitigation IDs whose AIGF `mitigates` lists the risk
    status: str


@dataclass
class CoverageReport:
    architecture: str
    architecture_name: str | None
    aigf_source: dict[str, Any]
    use_case: dict[str, Any] | None
    expected_source: str
    expected_risks: list[str]
    controls: list[ControlSummary]
    risks: list[RiskRow]
    claims_gaps: list[str]
    catalogue_implied_gaps: list[str]
    findings: list[Finding] = field(default_factory=list)
    element_counts: dict[str, int] = field(default_factory=dict)
    control_use_count: int = 0

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def has_errors(self) -> bool:
        return self.count(ERROR) > 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["summary"] = {
            "errors": self.count(ERROR),
            "warnings": self.count(WARNING),
            "info": self.count(INFO),
            "result": "FAIL" if self.has_errors else "PASS",
            "evidence": "declared (from the CALM architecture; not runtime-verified)",
        }
        return d


def _ordered_unique(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def _num(aigf_id: str) -> tuple[str, int]:
    prefix, _, rest = aigf_id.partition("-")
    digits = re.match(r"\d+", rest)
    return (prefix, int(digits.group()) if digits else 10**9)


def _title(cat: Catalogue, aigf_id: str) -> str:
    item = cat.risks.get(aigf_id) or cat.mitigations.get(aigf_id)
    return f"{aigf_id} ({item['title']})" if item and item.get("title") else aigf_id


def _summarise_controls(arch: Architecture) -> list[ControlSummary]:
    by_key: dict[str, dict[str, list[str]]] = {}
    for cu in arch.control_uses:
        entry = by_key.setdefault(cu.control_key, {"mi": [], "ri": [], "el": []})
        entry["mi"].extend(cu.aigf_mitigations)
        entry["ri"].extend(cu.aigf_risks)
        entry["el"].append(f"{cu.element_type}:{cu.element_id}")
    return [
        ControlSummary(
            control_key=key,
            mitigations=tuple(_ordered_unique(v["mi"])),
            risks=tuple(_ordered_unique(v["ri"])),
            elements=tuple(_ordered_unique(v["el"])),
        )
        for key, v in sorted(by_key.items())
    ]


def compute_coverage(
    arch: Architecture, cat: Catalogue, expected_risks: list[str] | None = None
) -> CoverageReport:
    findings: list[Finding] = []
    unknown_seen: set[tuple[str, str]] = set()

    def unknown(aigf_id: str, where: str, *, control_key: str | None = None, kind: str = "ID") -> None:
        if (aigf_id, where) in unknown_seen:
            return
        unknown_seen.add((aigf_id, where))
        findings.append(
            Finding(
                UNKNOWN_ID,
                ERROR,
                f"{kind} {aigf_id} is referenced by {where} but does not exist in the AIGF catalogue "
                f"snapshot (commit {str(cat.source.get('commit', '?'))[:7]}); check for a typo or a "
                f"newer catalogue version.",
                risk_id=aigf_id if aigf_id.startswith("ri-") else None,
                mitigation_id=aigf_id if aigf_id.startswith("mi-") else None,
                control_key=control_key,
            )
        )

    def known(aigf_id: str) -> bool:
        return aigf_id in cat.risks or aigf_id in cat.mitigations

    # --- use case and expected risks ---------------------------------------------------------
    use_case: dict[str, Any] | None = None
    if arch.use_case_id:
        try:
            use_case = cat.use_case(arch.use_case_id)
        except KeyError:
            unknown(arch.use_case_id, "the architecture metadata (finos-use-case)", kind="Use case")

    if expected_risks is not None:
        expected = _ordered_unique(expected_risks)
        expected_source = "--expected-risks override"
    elif use_case is not None:
        expected = list(use_case.get("related_risks") or [])
        expected_source = f"AIGF use case {use_case['id']} related_risks"
    elif arch.use_case_id:
        expected = []
        expected_source = f"use case {arch.use_case_id} (not found in snapshot)"
    else:
        raise CoverageError(
            "the architecture names no AIGF use case (metadata `finos-use-case`); "
            "pass --expected-risks ri-1,ri-4,... to say which risks must be covered"
        )

    if use_case is not None and use_case.get("draft"):
        findings.append(
            Finding(
                DRAFT_REFERENCE,
                INFO,
                f"The architecture's use case {use_case['id']} ({use_case.get('title')}) is marked "
                f"Draft in AIGF, so its list of expected risks may still change.",
            )
        )

    where_expected = "--expected-risks" if expected_risks is not None else f"use case {arch.use_case_id}"
    for r in expected:
        if r not in cat.risks:
            unknown(r, f"the expected risks ({where_expected})", kind="Risk")

    # --- metadata-level references ---------------------------------------------------------------
    for i in (*arch.metadata_mitigations, *arch.metadata_risks):
        if not known(i):
            unknown(i, "the architecture metadata (aigf-mitigations / aigf-risks)")

    # --- controls ----------------------------------------------------------------------------------
    controls = _summarise_controls(arch)
    claimed: dict[str, list[str]] = {}
    implied: dict[str, list[str]] = {}

    for c in controls:
        for m in c.mitigations:
            if m not in cat.mitigations:
                unknown(m, f"control '{c.control_key}' (aigf-mitigations)", control_key=c.control_key, kind="Mitigation")
                continue
            for r in cat.mitigations[m].get("mitigates") or []:
                implied.setdefault(r, [])
                if m not in implied[r]:
                    implied[r].append(m)
        for r in c.risks:
            if r not in cat.risks:
                unknown(r, f"control '{c.control_key}' (aigf-risks)", control_key=c.control_key, kind="Risk")
            claimed.setdefault(r, []).append(c.control_key)

        # Draft references (mitigations and risks named by this control).
        for i in (*c.mitigations, *c.risks):
            item = cat.mitigations.get(i) or cat.risks.get(i)
            if item and item.get("draft"):
                findings.append(
                    Finding(
                        DRAFT_REFERENCE,
                        INFO,
                        f"Control '{c.control_key}' references {_title(cat, i)}, which is marked Draft in "
                        f"AIGF and may still change.",
                        risk_id=i if i.startswith("ri-") else None,
                        mitigation_id=i if i.startswith("mi-") else None,
                        control_key=c.control_key,
                        elements=c.elements,
                    )
                )

        # Unsupported claims: a claimed risk that none of the control's (known) mitigations lists.
        known_mis = [m for m in c.mitigations if m in cat.mitigations]
        for r in c.risks:
            if r not in cat.risks:
                continue
            if not c.mitigations:
                findings.append(
                    Finding(
                        UNSUPPORTED_CLAIM,
                        WARNING,
                        f"Control '{c.control_key}' claims to address {_title(cat, r)} but names no AIGF "
                        f"mitigation, so the claim can't be checked against the catalogue.",
                        risk_id=r,
                        control_key=c.control_key,
                        elements=c.elements,
                    )
                )
            elif known_mis and not any(r in (cat.mitigations[m].get("mitigates") or []) for m in known_mis):
                mis = ", ".join(known_mis)
                findings.append(
                    Finding(
                        UNSUPPORTED_CLAIM,
                        WARNING,
                        f"Control '{c.control_key}' claims mitigation {', '.join(_title(cat, m) for m in known_mis)} "
                        f"addresses {_title(cat, r)}, but AIGF does not list {r} among the risks {mis} mitigates.",
                        risk_id=r,
                        mitigation_id=known_mis[0] if len(known_mis) == 1 else None,
                        control_key=c.control_key,
                        elements=c.elements,
                    )
                )

        # Config-level IDs (e.g. requirement config "control-id": "mi-11").
        for cu in arch.control_uses:
            if cu.control_key != c.control_key:
                continue
            cid = cu.config.get("control-id")
            if isinstance(cid, str) and _AIGF_ID_RE.match(cid) and not known(cid):
                unknown(cid, f"control '{c.control_key}' requirement config (control-id)", control_key=c.control_key)

    # --- gaps and possibly-covered -------------------------------------------------------------
    known_expected = [r for r in expected if r in cat.risks]
    claims_gaps = [r for r in known_expected if r not in claimed]
    implied_gaps = [r for r in known_expected if r not in implied]

    for r in claims_gaps:
        uc_label = f"use case {use_case['id']}" if use_case and expected_risks is None else "this architecture"
        findings.append(
            Finding(
                GAP,
                ERROR,
                f"{_title(cat, r)} is expected for {uc_label}, but no control in the architecture claims to "
                f"address it.",
                risk_id=r,
            )
        )
        if r in implied:
            mis = implied[r]
            findings.append(
                Finding(
                    POSSIBLY_COVERED,
                    WARNING,
                    f"AIGF says {', '.join(_title(cat, m) for m in mis)}, which the architecture already uses, "
                    f"mitigates {_title(cat, r)}, but no control claims it; confirm and add {r} to that "
                    f"control's aigf-risks, or record why it does not apply.",
                    risk_id=r,
                    mitigation_id=mis[0] if len(mis) == 1 else None,
                )
            )

    # --- per-risk rows -------------------------------------------------------------------------------
    row_ids = _ordered_unique([*expected, *sorted(claimed, key=_num)])
    rows: list[RiskRow] = []
    for r in row_ids:
        is_expected = r in expected
        claimers = tuple(claimed.get(r, []))
        impliers = tuple(implied.get(r, []))
        if r not in cat.risks:
            status = "UNKNOWN ID"
        elif not is_expected:
            status = "claimed (not expected)"
        elif claimers:
            supported = any(
                r in (cat.mitigations.get(m, {}).get("mitigates") or [])
                for c in controls
                if c.control_key in claimers
                for m in c.mitigations
            )
            status = "covered" if supported else "covered (unsupported claim only)"
        elif impliers:
            status = "GAP (possibly covered)"
        else:
            status = "GAP"
        rows.append(RiskRow(r, (cat.risks.get(r) or {}).get("title"), is_expected, claimers, impliers, status))

    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.finding_type, _num(f.risk_id or f.mitigation_id or "zz-0")))

    counts = {"node": 0, "relationship": 0, "flow": 0}
    for t in counts:
        counts[t] = len(arch.elements_with_controls(t))

    return CoverageReport(
        architecture=arch.path,
        architecture_name=arch.name,
        aigf_source=dict(cat.source),
        use_case=use_case,
        expected_source=expected_source,
        expected_risks=expected,
        controls=controls,
        risks=rows,
        claims_gaps=claims_gaps,
        catalogue_implied_gaps=implied_gaps,
        findings=findings,
        element_counts=counts,
        control_use_count=len(arch.control_uses),
    )
