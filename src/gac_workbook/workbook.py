"""Excel evidence workbook (openpyxl) and Markdown summary.

Sheets: Summary, Traceability, Findings, Evidence Checklist, Sources.
All evidence is *declared* in the CALM architecture; nothing is verified at runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from . import __version__
from .aigf import Catalogue
from .calm import Architecture, ControlUse
from .coverage import ERROR, INFO, WARNING, CoverageReport

SHEETS = ["Summary", "Traceability", "Findings", "Evidence Checklist", "Sources"]
EVIDENCE_LABEL = "Declared (not verified)"
TOOL_REPO = "https://github.com/jiaxingxue/gac-evidence-workbook"

TRACEABILITY_HEADERS = [
    "Risk ID", "Risk title", "Expected", "Coverage basis", "Control", "Mitigation ID", "Mitigation title",
    "Element type", "Element ID", "Element name", "Requirement URL", "Evidence status",
    "Candidate AIGF mitigations",
]

# Coverage basis labels (Traceability sheet).
BASIS_SUPPORTED = "Claimed & AIGF-supported"
BASIS_UNSUPPORTED = "Claimed – not in AIGF (unsupported)"
BASIS_IMPLIED = "Not claimed – AIGF suggests may cover"
BASIS_ADDITIONAL = "Additional AIGF-suggested coverage (not claimed)"  # implied, but the risk is already Covered
BASIS_GAP = "GAP – nothing addresses this risk"
NO_COVERAGE_TEXT = "No control or mitigation in this architecture addresses this risk"
_BASIS_RAG = {BASIS_SUPPORTED: "green", BASIS_UNSUPPORTED: "amber", BASIS_IMPLIED: "amber",
              BASIS_ADDITIONAL: "blue", BASIS_GAP: "red"}
_BASIS_ORDER = {BASIS_SUPPORTED: 0, BASIS_UNSUPPORTED: 1, BASIS_IMPLIED: 2, BASIS_ADDITIONAL: 2, BASIS_GAP: 3}
FINDINGS_HEADERS = [
    "#", "Severity", "Type", "Risk", "Mitigation", "Control", "Element(s)", "Explanation",
    "Recommended action", "Owner", "Action", "Due date", "Status",
]
CHECKLIST_HEADERS = [
    "#", "Control", "Mitigation(s)", "Claimed risks", "Element type", "Element ID", "Element name",
    "Requirement URL", "Evidence required (declared)", "Evidence status",
    "Evidence location", "Reviewer", "Date reviewed", "Result",
]
SOURCES_HEADERS = ["Source", "Role", "Repository / location", "Commit / version", "License", "Attribution / notes"]

# Requirement-config keys that identify the control rather than describe evidence.
_CONFIG_IDENTITY_KEYS = {"control-id", "name", "description", "aigf-catalog-url"}

# --- styles -------------------------------------------------------------------------------------
_NAVY = "1F3864"
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor=_NAVY)
_AUDITOR_FILL = PatternFill("solid", fgColor="FFF8E1")  # pale yellow: columns for the reviewer to fill
_AUDITOR_HEADER_FILL = PatternFill("solid", fgColor="7F6000")
_TITLE_FONT = Font(bold=True, size=16, color=_NAVY)
_SECTION_FONT = Font(bold=True, size=12, color=_NAVY)
_LABEL_FONT = Font(bold=True)
_NOTE_FONT = Font(italic=True, color="595959")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_WRAP_TOP = Alignment(wrap_text=True, vertical="top")
_TOP = Alignment(vertical="top")

_RAG = {
    "red": (PatternFill("solid", fgColor="FFC7CE"), Font(color="9C0006", bold=True)),
    "amber": (PatternFill("solid", fgColor="FFEB9C"), Font(color="9C5700", bold=True)),
    "green": (PatternFill("solid", fgColor="C6EFCE"), Font(color="006100", bold=True)),
    "blue": (PatternFill("solid", fgColor="DDEBF7"), Font(color="1F4E78", bold=True)),
}
# Info is not "good", so it is shown in neutral blue rather than green.
_SEVERITY_RAG = {ERROR: "red", WARNING: "amber", INFO: "blue"}


def _status_rag(status: str) -> str:
    s = status.lower()
    if s.startswith("gap") or s.startswith("unknown"):
        return "red"
    if "unsupported" in s or "not expected" in s:
        return "amber"
    return "green"


def _row_height(texts_and_widths: Iterable[tuple[Any, float]], line_height: float = 15.0) -> float:
    """Estimate a row height that shows all wrapped text (openpyxl cannot auto-fit rows).

    Assumes ~1 character per unit of column width, with a small margin for proportional fonts.
    """
    lines = 1
    for text, width in texts_and_widths:
        chars_per_line = max(1.0, width * 0.95 - 1)
        n = sum(max(1, math.ceil(len(part) / chars_per_line)) for part in str(text or "").split("\n"))
        lines = max(lines, n)
    return lines * line_height + 3


def _paint(cell, rag: str) -> None:
    fill, font = _RAG[rag]
    cell.fill, cell.font = fill, font


# --- provenance -----------------------------------------------------------------------------------
def _sanitize_url(url: str) -> str:
    # Drop any credentials embedded in a remote URL (https://user:token@host/...).
    return re.sub(r"^(https?://)[^/@]+@", r"\1", url.strip())


def architecture_provenance(path: str | Path) -> dict[str, Any]:
    """Git remote/commit of the repository holding the architecture file (if any) and its SHA-256."""
    p = Path(path)
    info: dict[str, Any] = {"file": str(path), "sha256": None, "repo": None, "commit": None, "dirty": None}
    try:
        info["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        pass

    def git(*args: str) -> str | None:
        try:
            res = subprocess.run(
                ["git", "-C", str(p.resolve().parent), *args], capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return res.stdout.strip() if res.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    if commit:
        info["commit"] = commit
        remote = git("config", "--get", "remote.origin.url")
        info["repo"] = _sanitize_url(remote) if remote else None
        status = git("status", "--porcelain", "--", str(p.resolve()))
        info["dirty"] = bool(status) if status is not None else None
    return info


# --- row builders ---------------------------------------------------------------------------------
@dataclass(frozen=True)
class TraceRow:
    risk_id: str
    risk_title: str
    expected: bool
    mitigation_id: str
    mitigation_title: str
    control: str
    element_type: str
    element_id: str
    element_name: str
    requirement_url: str
    evidence_status: str
    basis: str
    candidates: str = ""


def _num(aigf_id: str) -> int:
    m = re.match(r"^[a-z]+-(\d+)", aigf_id or "")
    return int(m.group(1)) if m else 10**9


def _element_uses(arch: Architecture) -> dict[tuple[str, str, str], list[ControlUse]]:
    """Group control uses by (control, element type, element id); a control may have several requirements."""
    grouped: dict[tuple[str, str, str], list[ControlUse]] = {}
    for cu in arch.control_uses:
        grouped.setdefault((cu.control_key, cu.element_type, cu.element_id), []).append(cu)
    return grouped


def traceability_rows(arch: Architecture, cat: Catalogue, report: CoverageReport) -> list[TraceRow]:
    expected = set(report.expected_risks)
    rows: list[TraceRow] = []

    def title(table: dict, i: str) -> str:
        return (table.get(i) or {}).get("title") or ""

    for (control, etype, eid), uses in _element_uses(arch).items():
        first = uses[0]
        req_urls = "\n".join(dict.fromkeys(u.requirement_url for u in uses if u.requirement_url))
        mis = list(first.aigf_mitigations) or [""]
        claimed = set(first.aigf_risks)
        candidates: dict[tuple[str, str], str] = {}
        for m in mis:
            mitigates = set((cat.mitigations.get(m) or {}).get("mitigates") or [])
            for r in claimed:
                candidates[(r, m)] = BASIS_SUPPORTED if r in mitigates else BASIS_UNSUPPORTED
            # Catalogue-implied rows are limited to expected risks the control does not claim.
            for r in (mitigates & expected) - claimed:
                candidates[(r, m)] = BASIS_IMPLIED
        for (r, m), basis in candidates.items():
            rows.append(
                TraceRow(
                    risk_id=r, risk_title=title(cat.risks, r), expected=r in expected,
                    mitigation_id=m, mitigation_title=title(cat.mitigations, m), control=control,
                    element_type=etype, element_id=eid, element_name=first.element_name or "",
                    requirement_url=req_urls, evidence_status=EVIDENCE_LABEL, basis=basis,
                )
            )

    # Implied rows for a risk that already has a claimed & AIGF-supported control are extra, not a concern.
    supported = {row.risk_id for row in rows if row.basis == BASIS_SUPPORTED}
    rows = [replace(row, basis=BASIS_ADDITIONAL) if row.basis == BASIS_IMPLIED and row.risk_id in supported else row
            for row in rows]

    traced = {row.risk_id for row in rows}
    risk_rows = {row.risk_id: row for row in report.risks}
    for r in report.expected_risks:
        if r not in traced:
            cands = risk_rows[r].candidates if r in risk_rows else ()
            rows.append(
                TraceRow(
                    risk_id=r, risk_title=title(cat.risks, r), expected=True, mitigation_id="–",
                    mitigation_title="–", control=NO_COVERAGE_TEXT, element_type="–", element_id="–",
                    element_name="–", requirement_url="–", evidence_status="None", basis=BASIS_GAP,
                    candidates="\n".join(cands) or "(AIGF lists no mitigation for this risk)",
                )
            )

    rows.sort(key=lambda t: (_num(t.risk_id), _BASIS_ORDER.get(t.basis, 9), _num(t.mitigation_id), t.control,
                             t.element_type, t.element_id))
    return rows


def _fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(_fmt_value(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))
    return str(v)


def evidence_required(config: dict[str, Any], limit: int = 900) -> str:
    """Summarise a requirement config: its description, then each declared parameter."""
    parts: list[str] = []
    if config.get("description"):
        parts.append(str(config["description"]))
    params = [f"{k}: {_fmt_value(v)}" for k, v in config.items() if k not in _CONFIG_IDENTITY_KEYS]
    if params:
        parts.append("Declared parameters: " + "; ".join(params))
    text = "\n".join(parts) or "(no requirement config declared)"
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --- sheet helpers --------------------------------------------------------------------------------
def _setup_print(ws: Worksheet, title: str, landscape: bool = True, header_row: int | None = 1) -> None:
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if header_row:
        ws.print_title_rows = f"{header_row}:{header_row}"
    ws.oddHeader.left.text = "Governance-as-Code Evidence Workbook"
    ws.oddHeader.right.text = title
    ws.oddFooter.left.text = f"gac-workbook {__version__} | Evidence declared, not verified"
    ws.oddFooter.right.text = "Page &P of &N"


def _write_table(
    ws: Worksheet,
    headers: list[str],
    rows: Iterable[list[Any]],
    widths: dict[str, float],
    wrap: Iterable[str] = (),
    auditor: Iterable[str] = (),
) -> int:
    wrap, auditor = set(wrap), set(auditor)
    ws.append(headers)
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col)
        c.font = _HEADER_FONT
        c.fill = _AUDITOR_HEADER_FILL if h in auditor else _HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = _BORDER
    n = 0
    for row in rows:
        ws.append(row)
        n += 1
        r = ws.max_row
        for col, h in enumerate(headers, start=1):
            c = ws.cell(row=r, column=col)
            c.alignment = _WRAP_TOP if h in wrap else _TOP
            c.border = _BORDER
            if h in auditor:
                c.fill = _AUDITOR_FILL
    for col, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(col)].width = widths.get(h, 14)
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"
    last = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A1:{last}{max(1, n + 1)}"
    return n


def _col(headers: list[str], name: str) -> int:
    return headers.index(name) + 1


def _link(cell, url: str | None) -> None:
    if url:
        cell.hyperlink = url
        cell.font = Font(color="0563C1", underline="single")


# --- sheets ---------------------------------------------------------------------------------------
def _summary_sheet(ws: Worksheet, arch: Architecture, cat: Catalogue, report: CoverageReport,
                   prov: dict[str, Any], generated_at: str) -> None:
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 44
    for col in "CDEF":
        ws.column_dimensions[col].width = 22

    ws["A1"] = "Governance-as-Code Evidence Workbook"
    ws["A1"].font = _TITLE_FONT
    ws["A2"] = ("Traceability of FINOS AI Governance Framework (AIGF) risks to controls declared in a FINOS CALM "
                "architecture. Evidence is as declared in the architecture and has not been verified at runtime.")
    ws["A2"].font = _NOTE_FONT
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 32

    expected = report.expected_risks
    claimed_expected = [r.risk_id for r in report.risks if r.expected and r.claimed_by]
    uc = report.use_case
    aigf = report.aigf_source

    facts: list[tuple[str, Any]] = [
        ("Coverage result", report.result_label),
        ("Architecture", arch.name or arch.unique_id or ""),
        ("Architecture file", prov.get("file")),
        ("Architecture ID", arch.unique_id or ""),
        ("CALM schema", arch.schema or ""),
        ("AIGF use case", f"{uc['id']} - {uc.get('title')}{' [Draft]' if uc.get('draft') else ''}" if uc else
         (arch.use_case_id or "(none)")),
        ("Expected risks source", report.expected_source),
        ("Expected risks", len(expected)),
        ("Expected risks claimed by a control", len(claimed_expected)),
        ("Claims-based gaps (errors)", len(report.claims_gaps)),
        ("Catalogue-implied gaps (info)", len(report.catalogue_implied_gaps)),
        ("Findings: errors", report.count(ERROR)),
        ("Findings: warnings", report.count(WARNING)),
        ("Findings: info", report.count(INFO)),
        ("Controls / control uses", f"{len(report.controls)} controls, {report.control_use_count} uses on "
         f"{report.element_counts.get('node', 0)} nodes, {report.element_counts.get('relationship', 0)} "
         f"relationships, {report.element_counts.get('flow', 0)} flows"),
        ("Evidence status", EVIDENCE_LABEL),
        ("Generated at (UTC)", generated_at),
        ("Tool version", f"gac-workbook {__version__}"),
        ("AIGF snapshot commit", aigf.get("commit")),
        ("Architecture repo commit", prov.get("commit") or "(not in a git repository)"),
        ("Architecture file SHA-256", prov.get("sha256")),
    ]
    r = 4
    ws.cell(row=r, column=1, value="Key facts").font = _SECTION_FONT
    r += 1
    for label, value in facts:
        a = ws.cell(row=r, column=1, value=label)
        b = ws.cell(row=r, column=2, value=value)
        a.font = _LABEL_FONT
        a.border = b.border = _BORDER
        a.alignment = _TOP
        b.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
        if label == "Coverage result":
            rag = "red" if report.has_errors else "green"
            _paint(b, rag)
            b.font = Font(bold=True, size=12, color=_RAG[rag][1].color)
        if label in ("Claims-based gaps (errors)", "Findings: errors") and value:
            _paint(b, "red")
        if label == "Findings: warnings" and value:
            _paint(b, "amber")
        if label == "AIGF use case" and uc:
            _link(b, uc.get("url"))
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Expected risk coverage").font = _SECTION_FONT
    r += 1
    cov_headers = ["Risk", "Title", "Claimed by", "AIGF-implied via", "Status"]
    for col, h in enumerate(cov_headers, start=1):
        c = ws.cell(row=r, column=col, value=h)
        c.font, c.fill, c.border = _HEADER_FONT, _HEADER_FILL, _BORDER
    r += 1
    for row in report.risks:
        values = [row.risk_id, row.title or "", ", ".join(row.claimed_by) or "-", ", ".join(row.implied_by) or "-",
                  row.status]
        for col, v in enumerate(values, start=1):
            c = ws.cell(row=r, column=col, value=v)
            c.border = _BORDER
            c.alignment = _WRAP_TOP
        _link(ws.cell(row=r, column=1), (cat.risks.get(row.risk_id) or {}).get("url"))
        _paint(ws.cell(row=r, column=5), _status_rag(row.status))
        ws.row_dimensions[r].height = _row_height(
            (v, ws.column_dimensions[get_column_letter(col)].width) for col, v in enumerate(values, start=1)
        )
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="How to read this workbook").font = _SECTION_FONT
    notes = [
        f"Traceability: one row per risk, control, mitigation and architecture element. Coverage basis: "
        f"'{BASIS_SUPPORTED}' = the control claims the risk and AIGF agrees; '{BASIS_UNSUPPORTED}' = the control "
        f"claims it but AIGF does not list the risk for that mitigation; '{BASIS_IMPLIED}' = AIGF says a mitigation "
        f"the control uses covers the risk, but the control does not claim it; '{BASIS_GAP}' = no control claims "
        f"the risk and no mitigation in use covers it (candidate AIGF mitigations are listed).",
        f"'{BASIS_ADDITIONAL}' (light blue) = the risk is already covered by a claimed & AIGF-supported control; "
        f"AIGF says another mitigation in use also covers it. This is extra context, not a finding. Amber "
        f"'{BASIS_IMPLIED}' is used only for risks with no supported claim.",
        "Findings: errors fail the CI check (gaps, unknown IDs); warnings and info do not. Owner / Action / Due date / "
        "Status (shaded) are for the reviewer.",
        "Evidence Checklist: one row per declared control requirement. Evidence location / Reviewer / Date reviewed / "
        "Result (shaded) are for the reviewer.",
        "A risk counts as covered when at least one control claims it and at least one claim is supported by AIGF "
        "(docs/decisions.md, D5).",
    ]
    for note in notes:
        r += 2  # blank line before each paragraph
        c = ws.cell(row=r, column=1, value=note)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        notes_width = sum(ws.column_dimensions[get_column_letter(col)].width for col in range(1, 7))
        ws.row_dimensions[r].height = max(32, _row_height([(note, notes_width)]))
    _setup_print(ws, "Summary", landscape=False, header_row=None)


def _traceability_sheet(ws: Worksheet, rows: list[TraceRow], cat: Catalogue) -> None:
    h = TRACEABILITY_HEADERS
    _write_table(
        ws, h,
        ([t.risk_id, t.risk_title, "yes" if t.expected else "no", t.basis, t.control, t.mitigation_id,
          t.mitigation_title, t.element_type, t.element_id, t.element_name, t.requirement_url, t.evidence_status,
          t.candidates] for t in rows),
        widths={"Risk ID": 9, "Risk title": 30, "Expected": 10, "Coverage basis": 24, "Control": 30,
                "Mitigation ID": 13, "Mitigation title": 30, "Element type": 13, "Element ID": 30,
                "Element name": 28, "Requirement URL": 44, "Evidence status": 22, "Candidate AIGF mitigations": 48},
        wrap={"Risk title", "Coverage basis", "Control", "Mitigation title", "Element name", "Requirement URL",
              "Candidate AIGF mitigations"},
    )
    gap_fill = _RAG["red"][0]
    for i, t in enumerate(rows, start=2):
        if t.basis == BASIS_GAP:
            for col in range(1, len(h) + 1):
                ws.cell(row=i, column=col).fill = gap_fill
        _link(ws.cell(row=i, column=_col(h, "Risk ID")), (cat.risks.get(t.risk_id) or {}).get("url"))
        _link(ws.cell(row=i, column=_col(h, "Mitigation ID")), (cat.mitigations.get(t.mitigation_id) or {}).get("url"))
        _paint(ws.cell(row=i, column=_col(h, "Coverage basis")), _BASIS_RAG.get(t.basis, "red"))
    _setup_print(ws, "Traceability")


def _findings_sheet(ws: Worksheet, report: CoverageReport) -> None:
    h = FINDINGS_HEADERS
    auditor = {"Owner", "Action", "Due date", "Status"}
    n = _write_table(
        ws, h,
        ([i, f.severity.upper(), f.finding_type, f.risk_id or "", f.mitigation_id or "", f.control_key or "",
          "\n".join(f.elements), f.message, f.recommended_action, None, None, None, None]
         for i, f in enumerate(report.findings, start=1)),
        widths={"#": 5, "Severity": 11, "Type": 20, "Risk": 8, "Mitigation": 11, "Control": 24, "Element(s)": 30,
                "Explanation": 60, "Recommended action": 45, "Owner": 16, "Action": 30, "Due date": 12,
                "Status": 14},
        wrap={"Type", "Element(s)", "Explanation", "Recommended action", "Action"},
        auditor=auditor,
    )
    for i, f in enumerate(report.findings, start=2):
        _paint(ws.cell(row=i, column=_col(h, "Severity")), _SEVERITY_RAG[f.severity])
        ws.cell(row=i, column=_col(h, "Due date")).number_format = "yyyy-mm-dd"
    if n:
        dv = DataValidation(type="list", formula1='"Open,In progress,Resolved,Risk accepted"', allow_blank=True)
        dv.add(f"{get_column_letter(_col(h, 'Status'))}2:{get_column_letter(_col(h, 'Status'))}{n + 1}")
        ws.add_data_validation(dv)
    _setup_print(ws, "Findings")


def _checklist_sheet(ws: Worksheet, arch: Architecture) -> None:
    h = CHECKLIST_HEADERS
    auditor = {"Evidence location", "Reviewer", "Date reviewed", "Result"}
    uses = sorted(arch.control_uses, key=lambda u: (u.control_key, u.element_type, u.element_id))
    n = _write_table(
        ws, h,
        ([i, u.control_key, ", ".join(u.aigf_mitigations), ", ".join(u.aigf_risks), u.element_type, u.element_id,
          u.element_name or "", u.requirement_url or "", evidence_required(u.config), EVIDENCE_LABEL,
          None, None, None, None]
         for i, u in enumerate(uses, start=1)),
        widths={"#": 5, "Control": 26, "Mitigation(s)": 13, "Claimed risks": 16, "Element type": 13,
                "Element ID": 28, "Element name": 26, "Requirement URL": 40, "Evidence required (declared)": 70,
                "Evidence status": 22, "Evidence location": 30, "Reviewer": 16, "Date reviewed": 14, "Result": 10},
        wrap={"Element name", "Requirement URL", "Evidence required (declared)", "Evidence location"},
        auditor=auditor,
    )
    for i in range(2, n + 2):
        ws.cell(row=i, column=_col(h, "Date reviewed")).number_format = "yyyy-mm-dd"
    if n:
        col = get_column_letter(_col(h, "Result"))
        dv = DataValidation(type="list", formula1='"Pass,Fail,N/A"', allow_blank=True,
                            showErrorMessage=True, errorTitle="Result", error="Choose Pass, Fail or N/A.")
        dv.add(f"{col}2:{col}{n + 1}")
        ws.add_data_validation(dv)
    _setup_print(ws, "Evidence Checklist")


def _sources_sheet(ws: Worksheet, arch: Architecture, report: CoverageReport, prov: dict[str, Any]) -> None:
    aigf = report.aigf_source
    commit = aigf.get("commit") or ""
    rows = [
        ["FINOS AI Governance Framework (AIGF)", "Reference catalogue: risks, mitigations, use cases",
         aigf.get("repo"), commit, aigf.get("license"),
         f"{aigf.get('attribution')}. Snapshot of IDs, titles, status, links and catalogue URLs only; no body text. "
         f"Catalogue: {aigf.get('catalogue_site')}. License: https://creativecommons.org/licenses/by/4.0/"],
        ["CALM architecture", "Input: controls and their declared AIGF mappings",
         prov.get("repo") or prov.get("file"), prov.get("commit") or "(not in a git repository)",
         "Not determined by this tool; see the source repository",
         f"File: {prov.get('file')}; SHA-256: {prov.get('sha256')}"
         + ("; working copy has local changes" if prov.get("dirty") else "")],
        ["FINOS CALM schema", "Architecture format", arch.schema or "", "", "Apache-2.0 (FINOS)", ""],
        ["gac-workbook", "Tool that generated this workbook", TOOL_REPO, __version__, "Apache-2.0", ""],
    ]
    _write_table(
        ws, SOURCES_HEADERS, rows,
        widths={"Source": 32, "Role": 34, "Repository / location": 48, "Commit / version": 44, "License": 26,
                "Attribution / notes": 70},
        wrap=set(SOURCES_HEADERS),
    )
    for i, r in enumerate(rows, start=2):
        if isinstance(r[2], str) and r[2].startswith("http"):
            _link(ws.cell(row=i, column=3), r[2])
    _setup_print(ws, "Sources")


# --- public API -----------------------------------------------------------------------------------
def build_workbook(arch: Architecture, cat: Catalogue, report: CoverageReport, *,
                   generated_at: str | None = None, provenance: dict[str, Any] | None = None) -> Workbook:
    generated_at = generated_at or _now()
    prov = provenance if provenance is not None else architecture_provenance(arch.path)
    wb = Workbook()
    wb.properties.title = "Governance-as-Code Evidence Workbook"
    wb.properties.creator = f"gac-workbook {__version__}"
    _summary_sheet(wb.active, arch, cat, report, prov, generated_at)
    _traceability_sheet(wb.create_sheet("Traceability"), traceability_rows(arch, cat, report), cat)
    _findings_sheet(wb.create_sheet("Findings"), report)
    _checklist_sheet(wb.create_sheet("Evidence Checklist"), arch)
    _sources_sheet(wb.create_sheet("Sources"), arch, report, prov)
    return wb


def _md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def summary_markdown(arch: Architecture, report: CoverageReport, *, generated_at: str,
                     provenance: dict[str, Any]) -> str:
    uc = report.use_case
    aigf = report.aigf_source
    lines = [
        "# Governance-as-Code evidence summary",
        "",
        f"**Coverage result: {report.result_label}**",
        "",
        f"Findings: {report.count(ERROR)} error, {report.count(WARNING)} warning, {report.count(INFO)} info.",
        "",
        f"- Architecture: {arch.name or arch.unique_id} (`{provenance.get('file')}`)",
        f"- AIGF use case: {uc['id'] + ' - ' + str(uc.get('title')) + (' [Draft]' if uc.get('draft') else '') if uc else '(none)'}",
        f"- Expected risks ({report.expected_source}): {', '.join(report.expected_risks) or '(none)'}",
        f"- Claims-based gaps: {', '.join(report.claims_gaps) or 'none'}",
        f"- Catalogue-implied gaps: {', '.join(report.catalogue_implied_gaps) or 'none'}",
        f"- Evidence: {EVIDENCE_LABEL}",
        "",
        "## Expected risk coverage",
        "",
        "| Risk | Title | Claimed by | AIGF-implied via | Status |",
        "|---|---|---|---|---|",
    ]
    for r in report.risks:
        lines.append(f"| {r.risk_id} | {_md_escape(r.title or '')} | {', '.join(r.claimed_by) or '-'} | "
                     f"{', '.join(r.implied_by) or '-'} | {r.status} |")
    lines += ["", "## Findings", "", "| Severity | Type | Subject | Explanation | Recommended action |",
              "|---|---|---|---|---|"]
    for f in report.findings:
        lines.append(f"| {f.severity.upper()} | {f.finding_type} | {f.risk_id or f.mitigation_id or '-'} | "
                     f"{_md_escape(f.message)} | {_md_escape(f.recommended_action)} |")
    lines += [
        "",
        "## Sources",
        "",
        f"- AIGF: {aigf.get('repo')} @ `{aigf.get('commit')}`. {aigf.get('attribution')} "
        f"(https://creativecommons.org/licenses/by/4.0/). IDs, titles and links only.",
        f"- Architecture: {provenance.get('repo') or provenance.get('file')} @ "
        f"`{provenance.get('commit') or 'n/a'}`; file SHA-256 `{provenance.get('sha256')}`",
        f"- Generated {generated_at} by gac-workbook {__version__}",
        "",
    ]
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def export(arch: Architecture, cat: Catalogue, report: CoverageReport, out_xlsx: Path,
           out_md: Path | None = None, *, generated_at: str | None = None) -> tuple[Path, Path]:
    generated_at = generated_at or _now()
    prov = architecture_provenance(arch.path)
    out_xlsx = Path(out_xlsx)
    out_md = Path(out_md) if out_md else out_xlsx.with_name("summary.md")
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(arch, cat, report, generated_at=generated_at, provenance=prov).save(out_xlsx)
    out_md.write_text(summary_markdown(arch, report, generated_at=generated_at, provenance=prov),
                      encoding="utf-8", newline="\n")
    return out_xlsx, out_md
