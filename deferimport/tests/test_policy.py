from __future__ import annotations

import pytest

from deferimport.policy import Policy, parse


def test_everything_takes_every_import():
    assert parse("everything")("a", "b", None)
    assert parse("")("a", "b", ("c",))


def test_importers_take_only_imports_their_modules_make():
    policy = parse("importers=pymux,ptterm")
    assert policy("pymux.server", "anyio", None)
    assert policy("ptterm", "pyte", ("Screen",))
    assert not policy("pymuxish", "anyio", None)
    assert not policy(None, "anyio", None)


def test_targets_take_only_their_modules():
    policy = parse("targets=anyio")
    assert policy("x", "anyio.abc", None)
    assert not policy("x", "aiosqlite", None)


def test_deny_wins_and_catches_a_submodule_named_in_a_fromlist():
    policy = parse("importers=pymux;deny=pymux.commands")
    assert not policy("pymux.main", "pymux.commands.kill_pane", None)
    assert not policy("pymux.main", "pymux", ("commands",))
    assert policy("pymux.main", "pymux", ("layout",))


def test_a_spec_round_trips():
    for spec in ("everything", "importers=a,b", "deny=c;importers=a;targets=t"):
        assert parse(parse(spec).spec()) == parse(spec)


def test_an_unknown_field_is_refused():
    with pytest.raises(ValueError, match="unknown policy field"):
        parse("importer=a")


def test_covers_importer():
    assert Policy().covers_importer("anything")
    assert not parse("importers=a").covers_importer("b")
