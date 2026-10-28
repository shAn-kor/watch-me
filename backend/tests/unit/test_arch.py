"""UT-ARCH-01..03: architecture rules (07 section 3.1)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"


def _lint_imports(cwd: Path) -> subprocess.CompletedProcess[str]:
    exe = Path(sys.executable).parent / "lint-imports"
    assert exe.exists(), "import-linter is not installed in this environment"
    return subprocess.run(
        [str(exe)], cwd=cwd, capture_output=True, text=True, timeout=120
    )


def test_ut_arch_01_import_layering_passes():
    """UT-ARCH-01: the contracts from 06 section 2 hold for the real tree."""
    result = _lint_imports(BACKEND)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("bad_file", "line", "contract_fragment"),
    [
        ("app/api/_bad.py", "import app.repositories", "api must not import"),
        ("app/ai/_bad.py", "import app.db", "ai has no DB"),
        ("app/ai/_bad2.py", "import app.models", "ai has no DB"),
        ("app/ai/_bad3.py", "import app.services", "ai has no DB"),
        ("app/services/_bad.py", "import app.pipeline", "services must not import"),
        ("app/pipeline/_bad.py", "import app.repositories", "pipeline must not import"),
        (
            "app/repositories/_bad.py",
            "import app.services",
            "repositories must not import",
        ),
        (
            "app/models/_bad.py",
            "import app.domain.situations",
            "models may import only",
        ),
        ("app/domain/_bad.py", "import sqlalchemy", "domain imports stdlib only"),
        ("app/storage/_bad.py", "import app.errors", "storage imports stdlib only"),
        ("app/security/_bad.py", "import app.services", "security must not import"),
        ("app/services/_bad2.py", "import app.container", "only entry points"),
    ],
)
def test_ut_arch_01_violations_are_detected(
    tmp_path, bad_file, line, contract_fragment
):
    """UT-ARCH-01 (negative): each forbidden edge named in 06 section 2 fails."""
    work = tmp_path / "backend"
    work.mkdir()
    shutil.copytree(
        APP, work / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    shutil.copy(BACKEND / "pyproject.toml", work / "pyproject.toml")
    target = work / bad_file
    target.write_text(f"{line}\n", encoding="utf-8")
    result = _lint_imports(work)
    assert result.returncode != 0, "violation went unnoticed:\n" + result.stdout
    assert contract_fragment in result.stdout


def test_ut_arch_01_every_layer_rule_has_a_contract():
    """UT-ARCH-01 (meta): one contract per layer row of 06 section 2."""
    import tomllib

    data = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = data["tool"]["importlinter"]["contracts"]
    sources: set[str] = set()
    for c in contracts:
        sources.update(c["source_modules"])
    for layer in (
        "app.api",
        "app.services",
        "app.pipeline",
        "app.repositories",
        "app.models",
        "app.ai",
        "app.storage",
        "app.domain",
        "app.security",
    ):
        assert layer in sources, f"no import-linter contract for {layer}"


_CONFIRMED_QUERY = re.compile(
    r"""(status\s*==\s*["']confirmed["']|FactStatus\.CONFIRMED|["']confirmed["'])"""
)


def test_ut_arch_02_public_facts_is_the_only_reader():
    """UT-ARCH-02: no confirmed-fact queries in the public/Q&A/media services (I-1, I-14)."""
    guarded = [
        APP / "services" / "public_profile_service.py",
        APP / "services" / "qa_service.py",
        APP / "services" / "media_access_service.py",
    ]
    offenders = [
        str(p.relative_to(BACKEND))
        for p in guarded
        if p.exists() and _CONFIRMED_QUERY.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"read confirmed facts outside public_facts: {offenders}"


def test_ut_arch_03_ip_hash_never_contains_the_ip(caplog):
    """UT-ARCH-03 (helper level): the hash helper output carries no raw IP."""
    import logging
    from datetime import date

    from app.logging import ip_hash

    ip = "203.0.113.77"
    digest = ip_hash("k" * 32, ip, date(2026, 10, 28))
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert ip not in digest
    # Same key/date/ip is stable; another day changes it (rate-limit window).
    assert digest == ip_hash("k" * 32, ip, date(2026, 10, 28))
    assert digest != ip_hash("k" * 32, ip, date(2026, 10, 29))
    with caplog.at_level(logging.INFO):
        logging.getLogger("app").info("client %s", digest)
    assert ip not in caplog.text

