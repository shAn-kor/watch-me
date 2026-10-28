"""Pipeline job handlers (lane P). `build_handlers` is what the worker registers."""

from __future__ import annotations

from app.config import Settings
from app.pipeline.handlers.check import CheckHandler
from app.pipeline.handlers.draft import DraftHandler
from app.pipeline.handlers.merge import MergeHandler
from app.pipeline.handlers.purge import PurgeClipHandler, PurgeDogHandler, RetentionSweepHandler
from app.pipeline.handlers.sample import SampleHandler
from app.pipeline.handlers.transcode import TranscodeHandler
from app.pipeline.handlers.transcribe import TranscribeHandler


def build_handlers(settings: Settings) -> list:
    return [
        TranscodeHandler(settings),
        TranscribeHandler(settings),
        SampleHandler(settings),
        DraftHandler(settings),
        MergeHandler(settings),
        CheckHandler(settings),
        PurgeClipHandler(settings),
        PurgeDogHandler(settings),
        RetentionSweepHandler(settings),
    ]
