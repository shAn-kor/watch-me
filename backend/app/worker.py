"""Worker entry point (06 section 1): `python -m app.worker`.

Stub in Phase 0. Lane D adds `JobRunner`; lane P registers the handlers.
"""

from __future__ import annotations

import sys

from app.container import build_container
from app.logging import configure_logging


def main() -> int:
    container = build_container()
    configure_logging(container.settings.log_level)
    runner = container.pipeline.get("runner")
    if runner is None:
        print("worker: JobRunner is not wired yet (lane D / lane P)", file=sys.stderr)
        container.dispose()
        return 2
    try:
        runner.run_forever()  # [slot D] JobRunner.run_forever()
    finally:
        container.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
