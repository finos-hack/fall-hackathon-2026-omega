"""Command-line entry point. The `export` and `check` subcommands are added in a later task."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print("gac-workbook: the export and check commands are not implemented yet.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
