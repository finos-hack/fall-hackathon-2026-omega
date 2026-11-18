"""CLI tests: exit codes and output formats, on the synthetic fixtures."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT
from gac_workbook.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main


def _args(fixtures: Path, *extra: str) -> list[str]:
    return ["check", "--arch", str(fixtures / "mini.calm.json"), "--aigf", str(fixtures / "mini-aigf.json"), *extra]


def test_exit_1_when_errors(fixtures: Path, capsys) -> None:
    assert main(_args(fixtures)) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "Expected risks: ri-901, ri-902, ri-903" in out
    assert "[ERROR  ] GAP" in out
    assert "Coverage result: GAPS FOUND (1 error, 1 warning)" in out


def test_exit_0_when_only_warnings(fixtures: Path, capsys) -> None:
    # ri-902's claim is unsupported (warning) but claimed, so no claims-based gap.
    assert main(_args(fixtures, "--expected-risks", "ri-901,ri-902")) == EXIT_OK
    out = capsys.readouterr().out
    assert "UNSUPPORTED CLAIM" in out
    assert "Coverage result: NO GAPS FOUND" in out


def test_fail_on_policies(fixtures: Path, capsys) -> None:
    # Fixture default: 1 error (GAP), 1 warning (UNSUPPORTED CLAIM).
    assert main(_args(fixtures, "--fail-on", "error")) == EXIT_FINDINGS
    assert main(_args(fixtures, "--fail-on", "warning")) == EXIT_FINDINGS
    assert main(_args(fixtures, "--fail-on", "none")) == EXIT_OK
    # No errors, 1 warning.
    only_warn = ("--expected-risks", "ri-901,ri-902")
    assert main(_args(fixtures, *only_warn, "--fail-on", "error")) == EXIT_OK
    assert main(_args(fixtures, *only_warn, "--fail-on", "warning")) == EXIT_FINDINGS
    assert main(_args(fixtures, *only_warn, "--fail-on", "none")) == EXIT_OK
    out = capsys.readouterr().out
    assert "Exit policy    : --fail-on warning -> exit 1" in out


def test_fail_on_in_json(fixtures: Path, capsys) -> None:
    main(_args(fixtures, "--format", "json", "--fail-on", "none"))
    assert json.loads(capsys.readouterr().out)["check"] == {"fail_on": "none", "exit_code": 0}


def test_fail_on_rejects_unknown_value(fixtures: Path) -> None:
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(_args(fixtures, "--fail-on", "info"))
    assert exc.value.code == EXIT_USAGE


def test_exit_2_on_missing_file(fixtures: Path, tmp_path: Path, capsys) -> None:
    code = main(["check", "--arch", str(tmp_path / "missing.json"), "--aigf", str(fixtures / "mini-aigf.json")])
    assert code == EXIT_USAGE
    assert "error" in capsys.readouterr().err


def test_exit_2_when_no_use_case_and_no_override(fixtures: Path, tmp_path: Path, capsys) -> None:
    doc = json.loads((fixtures / "mini.calm.json").read_text(encoding="utf-8"))
    del doc["metadata"]
    p = tmp_path / "no-uc.calm.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["check", "--arch", str(p), "--aigf", str(fixtures / "mini-aigf.json")]) == EXIT_USAGE
    assert "--expected-risks" in capsys.readouterr().err


def test_json_format(fixtures: Path, capsys) -> None:
    assert main(_args(fixtures, "--format", "json")) == EXIT_FINDINGS
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == {
        "errors": 1,
        "warnings": 1,
        "info": 1,
        "coverage_result": "GAPS FOUND (1 error, 1 warning)",
        "evidence": "declared (from the CALM architecture; not runtime-verified)",
    }
    assert data["claims_gaps"] == ["ri-903"]
    assert {f["finding_type"] for f in data["findings"]} == {"GAP", "UNSUPPORTED CLAIM", "DRAFT REFERENCE"}
    assert all(f["recommended_action"] for f in data["findings"])


def test_text_output_shows_recommended_action(fixtures: Path, capsys) -> None:
    main(_args(fixtures))
    assert "Recommended action: Add or identify a control that addresses ri-903" in capsys.readouterr().out


def test_stdout_is_utf8_when_piped(fixtures: Path) -> None:
    """The committed snapshot's attribution contains '©'; piped output must carry it as UTF-8."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    proc = subprocess.run(
        [
            sys.executable, "-m", "gac_workbook.cli", "check",
            "--arch", str(fixtures / "mini.calm.json"),
            "--aigf", str(REPO_ROOT / "data" / "aigf-snapshot.json"),
            "--expected-risks", "ri-1",
        ],
        capture_output=True,
        env=env,
    )
    assert "© FINOS, CC-BY-4.0".encode("utf-8") in proc.stdout
    proc.stdout.decode("utf-8")  # whole stream is valid UTF-8
