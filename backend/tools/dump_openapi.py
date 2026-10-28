"""Write the app's OpenAPI JSON for the frontend contract check (FE-API-05).

    python -m tools.dump_openapi [OUTPUT]      # default: stdout

Builds the app with throwaway settings: an in-memory database, a temp storage
directory, fixed fake keys, no `.env` file, no network. The schema is read from
the route table; no request is served.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.config import Settings
from app.container import build_container
from app.main import create_app

_FAKE_KEY = "openapi-dump-not-a-real-key-0123456789abcdef"


def build_schema() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            _env_file=None,
            app_env="test",
            secret_key=_FAKE_KEY,
            ip_hash_key=_FAKE_KEY,
            database_url="sqlite://",
            storage_root=Path(tmp) / "storage",
            cookie_secure=False,
        )
        container = build_container(settings)
        try:
            schema = create_app(container, spa_dir=Path(tmp) / "spa").openapi()
        finally:
            container.dispose()
    # HEAD mirrors GET on the media routes and shares its operationId, whose
    # suffix (`_get` or `_head`) changes between runs. Drop HEAD and pin `_get`
    # so the output is the same on every run. The client never calls these.
    for item in schema["paths"].values():
        item.pop("head", None)
        get = item.get("get")
        if get and get.get("operationId", "").endswith("_head"):
            get["operationId"] = get["operationId"][: -len("_head")] + "_get"
    return schema


def main(argv: list[str]) -> int:
    text = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"
    if len(argv) > 1:
        Path(argv[1]).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
