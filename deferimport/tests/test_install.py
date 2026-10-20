from __future__ import annotations

import compileall
import shutil

import pytest

from probes import FIXTURES, MECHANISMS, run

LAZY = [mechanism for mechanism in MECHANISMS if mechanism != "eager"]

COUNT = """
load("app.plain")
from deferimport import hook
result = [ran(), dict(hook.STATS)]
"""


@pytest.mark.parametrize("mechanism", LAZY)
def test_a_cached_pyc_beside_the_source_is_bypassed(mechanism, tmp_path):
    # An installed package carries a `__pycache__` beside every source,
    # and a loader that reads it never runs the rewrite.
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    assert compileall.compile_dir(fixtures, quiet=1)
    ran, stats = run(mechanism, COUNT, fixtures=fixtures, cache=tmp_path / "cache")
    assert not ran
    assert stats["lazy"] >= 1


@pytest.mark.parametrize("mechanism", LAZY)
def test_the_second_start_reads_the_rewrite_from_the_cache(mechanism, tmp_path):
    first = run(mechanism, COUNT, cache=tmp_path)[1]
    second = run(mechanism, COUNT, cache=tmp_path)[1]
    assert first["cached"] == 0
    assert second["cached"] == second["modules"] >= 1
    assert second["lazy"] == first["lazy"]


@pytest.mark.parametrize("mechanism", LAZY)
def test_a_cache_that_cannot_be_written_costs_nothing_but_the_parse(mechanism, tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("")
    ran, stats = run(mechanism, COUNT, cache=blocked / "under-a-file")
    assert not ran
    assert stats["cached"] == 0


def test_eager_in_the_environment_installs_nothing(tmp_path):
    answer = run(
        "proxies",
        "import deferimport\nresult = [deferimport.installed() is None, ran() or load('app.plain') and ran()]",
        cache=tmp_path,
        env={"DEFERIMPORT": "eager"},
    )
    assert answer == [True, True]


def test_installing_twice_gives_the_first_finder(tmp_path):
    answer = run(
        "proxies",
        "import deferimport, sys\nfirst = deferimport.installed()\n"
        "result = [deferimport.install() is first, sum(f is first for f in sys.meta_path)]",
        cache=tmp_path,
    )
    assert answer == [True, 1]


def test_a_policy_that_takes_nothing_rewrites_nothing(tmp_path):
    stats = run("proxies", COUNT, policy="targets=nothing_by_this_name", cache=tmp_path)[1]
    assert stats["lazy"] == 0
