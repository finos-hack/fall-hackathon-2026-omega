from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PINNED_AIGF_COMMIT = "67b8c3257695d5ede09d262798bf28a0e58d4740"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def real_aigf_root() -> Path:
    """Local AIGF clone (not committed). Tests using it are skipped when it's absent."""
    root = Path(os.environ.get("AIGF_ROOT", REPO_ROOT.parent / "sources" / "ai-governance-framework"))
    if not (root / "docs" / "_risks").is_dir():
        pytest.skip(f"AIGF clone not found at {root}")
    return root
