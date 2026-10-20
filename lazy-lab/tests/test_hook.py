from __future__ import annotations

import compileall
import shutil

import pytest

from lazylab import available
from probes import FIXTURES, run

REWRITES = [name for name in ("ast-native", "ast-proxy") if name in available()]

COUNT = """
load("app.plain")
from lazylab import hook
result = [ran(), dict(hook.STATS)]
"""


@pytest.mark.parametrize("candidate", REWRITES)
def test_a_cached_pyc_beside_the_source_is_bypassed(candidate, tmp_path):
    # The store holds a `__pycache__` beside every source, and a loader
    # that reads it never runs the rewrite.
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    assert compileall.compile_dir(fixtures, quiet=1)
    ran, stats = run(candidate, COUNT, fixtures=fixtures)
    assert not ran
    assert stats["lazy"] >= 1


@pytest.mark.parametrize("candidate", REWRITES)
def test_the_second_run_reads_the_rewrite_from_the_cache(candidate, tmp_path):
    first = run(candidate, COUNT, cache=tmp_path)[1]
    second = run(candidate, COUNT, cache=tmp_path)[1]
    assert first["cached"] == 0
    assert second["cached"] == second["modules"] >= 1
    assert second["lazy"] == first["lazy"]


def test_a_policy_that_takes_nothing_rewrites_nothing(tmp_path):
    stats = run("ast-proxy", COUNT, policy="targets=nothing_by_this_name")[1]
    assert stats["lazy"] == 0
