"""Tests for `runme case save` (cases.save_case)."""
import os
import json

import pytest

from runme import cases
from runme.cli import load_overlay
from runme.namelist import Namelist


def _make_run(rundir, params):
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(rundir, cases.RECORD), "w") as f:
        json.dump({"params": params}, f)


def test_save_writes_namelist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rundir = str(tmp_path / "run0")
    _make_run(rundir, {"control.tau": 200, "control.n_accel": 9})

    dest = cases.save_case("spinup", rundir)
    assert dest == os.path.join("cases", "spinup.nml")

    saved = Namelist().load(open(dest))
    assert saved == {"control.tau": 200, "control.n_accel": 9}


def test_save_normalises_group_aliases(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rundir = str(tmp_path / "run0")
    _make_run(rundir, {"ctl.tau": 5})

    dest = cases.save_case("c", rundir, grp_aliases={"ctl": "control"})
    saved = Namelist().load(open(dest))
    assert saved == {"control.tau": 5}


def test_save_keeps_explicit_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rundir = str(tmp_path / "run0")
    _make_run(rundir, {"control.tau": 1})
    dest = cases.save_case("spinup.par", rundir)
    assert dest == os.path.join("cases", "spinup.par")


def test_save_errors_without_record(tmp_path):
    with pytest.raises(FileNotFoundError, match="not a runme run directory"):
        cases.save_case("x", str(tmp_path / "missing"))


def test_save_errors_with_no_params(tmp_path):
    rundir = str(tmp_path / "run0")
    _make_run(rundir, {})
    with pytest.raises(ValueError, match="no applied parameters"):
        cases.save_case("x", rundir)


def test_round_trip_save_then_use_as_overlay(tmp_path, monkeypatch):
    """A saved case resolves by name and reloads as an overlay dict."""
    monkeypatch.chdir(tmp_path)
    rundir = str(tmp_path / "run0")
    _make_run(rundir, {"control.tau": 42})
    cases.save_case("spinup", rundir)

    resolved = cases.resolve_par_path("spinup")
    overlay = load_overlay(resolved, {"par_path_as_argument": False})
    assert overlay == {"control.tau": 42}
