"""Fixtures of the lane P pipeline tests."""

from __future__ import annotations

import shutil

import pytest

from tests.pipeline.pipe_support import PipeEnv


def pytest_collection_modifyitems(config, items):
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        skip = pytest.mark.skip(reason="needs ffmpeg and ffprobe")
        for item in items:
            if "tests/pipeline" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture
def make_env(settings, clock, engine, seed):
    """`make_env(**kwargs) -> PipeEnv` (kwargs go to `PipeEnv`)."""

    def _make(**kwargs) -> PipeEnv:
        return PipeEnv(settings, clock, engine, seed, **kwargs)

    return _make


@pytest.fixture
def env(make_env) -> PipeEnv:
    return make_env()
