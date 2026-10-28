"""Worker entry point (06 section 1): `python -m app.worker`.

Stub in Phase 0. Lane D adds `JobRunner`; lane P registers the handlers.
"""

from __future__ import annotations

from app.container import Container, build_container
from app.logging import configure_logging
from app.pipeline.handlers import build_handlers
from app.pipeline.handlers.base import HandlerContext
from app.pipeline.runner import JobRunner


def build_runner(container: Container, *, worker_id: str = "worker-1", poll_s: float = 2.0) -> JobRunner:
    ctx = HandlerContext(
        settings=container.settings,
        storage=container.storage,
        ffmpeg=container.pipeline["ffmpeg"],
        ai=container.ai,
        services=container.services,
        clock=container.clock,
    )
    return JobRunner(
        container.services.job_queue,
        build_handlers(container.settings),
        ctx,
        container.clock,
        worker_id=worker_id,
        poll_s=poll_s,
    )


def main() -> int:
    container = build_container()
    configure_logging(container.settings.log_level)
    runner = build_runner(container)
    container.pipeline["runner"] = runner
    try:
        runner.run_forever()
    finally:
        container.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
