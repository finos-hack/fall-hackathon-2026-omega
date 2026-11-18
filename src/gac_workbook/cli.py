"""Command-line interface: `gac-workbook check` and `gac-workbook export`.

Exit codes: 0 = no errors, 1 = errors found (gaps or unknown IDs), 2 = usage or input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .aigf import load_snapshot
from .calm import CalmError, load_architecture
from .coverage import ERROR, INFO, WARNING, CoverageError, CoverageReport, compute_coverage

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2

_PACKAGED_SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "aigf-snapshot.json"


def _default_snapshot() -> Path:
    local = Path("data") / "aigf-snapshot.json"
    return local if local.is_file() else _PACKAGED_SNAPSHOT


def _parse_id_list(value: str) -> list[str]:
    ids = [v.strip() for v in value.split(",") if v.strip()]
    if not ids:
        raise argparse.ArgumentTypeError("expected a comma-separated list such as ri-1,ri-4")
    return ids


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines += [fmt.format(*r) for r in rows]
    return [line.rstrip() for line in lines]


def render_text(report: CoverageReport) -> str:
    src = report.aigf_source
    out: list[str] = []
    out.append(f"AIGF snapshot : {src.get('repo')} @ {str(src.get('commit'))[:12]}  ({src.get('attribution')})")
    out.append(f"Architecture  : {report.architecture}" + (f"  ({report.architecture_name})" if report.architecture_name else ""))
    uc = report.use_case
    if uc:
        draft = " [Draft]" if uc.get("draft") else ""
        out.append(f"Use case      : {uc['id']} - {uc.get('title')}{draft}")
    out.append(f"Expected risks: {', '.join(report.expected_risks) or '(none)'}  [{len(report.expected_risks)}, from {report.expected_source}]")
    ec = report.element_counts
    out.append(
        f"Controls      : {len(report.controls)} distinct, {report.control_use_count} uses on "
        f"{ec.get('node', 0)} nodes, {ec.get('relationship', 0)} relationships, {ec.get('flow', 0)} flows"
    )
    out.append("Evidence      : declared in the CALM architecture (not runtime-verified)")
    out.append("")

    out.append("Controls")
    out += _table(
        ["CONTROL", "MITIGATIONS", "CLAIMED RISKS", "ELEMENTS"],
        [[c.control_key, ", ".join(c.mitigations) or "-", ", ".join(c.risks) or "-", str(len(c.elements))] for c in report.controls],
    )
    out.append("")

    out.append("Risk coverage")
    out += _table(
        ["RISK", "TITLE", "EXPECTED", "CLAIMED BY", "AIGF-IMPLIED VIA", "STATUS"],
        [
            [
                r.risk_id,
                (r.title or "?")[:40],
                "yes" if r.expected else "no",
                ", ".join(r.claimed_by) or "-",
                ", ".join(r.implied_by) or "-",
                r.status,
            ]
            for r in report.risks
        ],
    )
    out.append("")
    out.append(f"Claims-based gaps      : {', '.join(report.claims_gaps) or 'none'}")
    out.append(f"Catalogue-implied gaps : {', '.join(report.catalogue_implied_gaps) or 'none'}  (info)")
    out.append("")

    e, w, i = report.count(ERROR), report.count(WARNING), report.count(INFO)
    out.append(f"Findings ({e} error, {w} warning, {i} info)")
    for f in report.findings:
        subject = f.risk_id or f.mitigation_id or "-"
        out.append(f"  [{f.severity.upper():7}] {f.finding_type:<29} {subject:<7} {f.message}")
        out.append(f"  {'':9} {'':29} {'':7} Recommended action: {f.recommended_action}")
    out.append("")
    out.append(f"Result: {'FAIL' if report.has_errors else 'PASS'} ({e} error{'s' if e != 1 else ''})")
    return "\n".join(out)


def _load(args: argparse.Namespace):
    arch = load_architecture(args.arch)
    cat = load_snapshot(args.aigf)
    report = compute_coverage(arch, cat, expected_risks=args.expected_risks)
    return arch, cat, report


_INPUT_ERRORS = (OSError, json.JSONDecodeError, CalmError, CoverageError, KeyError)


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        _, _, report = _load(args)
    except _INPUT_ERRORS as exc:
        print(f"gac-workbook check: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return EXIT_FINDINGS if report.has_errors else EXIT_OK


def _cmd_export(args: argparse.Namespace) -> int:
    from .workbook import export  # openpyxl is only needed for export

    try:
        arch, cat, report = _load(args)
        xlsx, md = export(arch, cat, report, args.out, args.summary)
    except _INPUT_ERRORS as exc:
        print(f"gac-workbook export: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    status = "FAIL" if report.has_errors else "PASS"
    print(f"Wrote {xlsx}")
    print(f"Wrote {md}")
    print(
        f"Status: {status} ({report.count(ERROR)} error, {report.count(WARNING)} warning, {report.count(INFO)} info). "
        "Export always exits 0 on success; use `check` to gate CI."
    )
    return EXIT_OK


def _add_input_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--arch", required=True, type=Path, help="CALM 1.2 architecture JSON")
    p.add_argument("--aigf", type=Path, default=None, help="AIGF snapshot JSON (default: data/aigf-snapshot.json)")
    p.add_argument(
        "--expected-risks",
        type=_parse_id_list,
        default=None,
        help="comma-separated AIGF risk IDs to expect, overriding the architecture's use case",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gac-workbook",
        description="Trace CALM controls to FINOS AI Governance Framework risks.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="report coverage findings; exit 1 if there are errors")
    _add_input_args(check)
    check.add_argument("--format", choices=["text", "json"], default="text")
    check.set_defaults(func=_cmd_check)

    exp = sub.add_parser("export", help="write the Excel evidence workbook and a Markdown summary")
    _add_input_args(exp)
    exp.add_argument("--out", type=Path, default=Path("out") / "evidence-workbook.xlsx",
                     help="workbook path (default: out/evidence-workbook.xlsx)")
    exp.add_argument("--summary", type=Path, default=None,
                     help="Markdown summary path (default: summary.md next to the workbook)")
    exp.set_defaults(func=_cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Always write UTF-8 (Windows pipes otherwise default to the ANSI code page, which
    # garbles the © in the attribution and other non-ASCII titles).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if getattr(args, "aigf", "unset") is None:
        args.aigf = _default_snapshot()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
