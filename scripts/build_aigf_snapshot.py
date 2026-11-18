"""Generate data/aigf-snapshot.json from a local clone of finos/ai-governance-framework.

Usage:
    python scripts/build_aigf_snapshot.py ../sources/ai-governance-framework \
        --expect-commit 67b8c3257695d5ede09d262798bf28a0e58d4740

The clone must have a clean working tree. Only IDs, titles, status, links and
catalogue URLs are written; no body text. AIGF content (c) FINOS, CC-BY-4.0.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from gac_workbook.aigf import build_snapshot

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "aigf-snapshot.json"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("aigf_root", type=Path, help="path to a clone of finos/ai-governance-framework")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output file (default: {DEFAULT_OUT})")
    parser.add_argument("--expect-commit", help="fail unless the clone's HEAD is this commit SHA")
    args = parser.parse_args(argv)

    commit = _git(args.aigf_root, "rev-parse", "HEAD")
    if args.expect_commit and commit != args.expect_commit:
        print(f"error: {args.aigf_root} is at {commit}, expected {args.expect_commit}", file=sys.stderr)
        return 1
    if _git(args.aigf_root, "status", "--porcelain"):
        print(f"error: {args.aigf_root} has local changes; snapshot must come from a clean commit", file=sys.stderr)
        return 1

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot = build_snapshot(args.aigf_root, commit=commit, generated_at=generated_at)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    drafts = [e["id"] for k in ("risks", "mitigations", "use_cases") for e in snapshot[k] if e["draft"]]
    print(f"wrote {args.out}")
    print(f"  commit      {commit}")
    print(f"  risks       {len(snapshot['risks'])}")
    print(f"  mitigations {len(snapshot['mitigations'])}")
    print(f"  use cases   {len(snapshot['use_cases'])}")
    print(f"  draft       {', '.join(drafts) or '(none)'}")
    for note in snapshot["parse_notes"]:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
