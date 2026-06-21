"""Tests for case-name resolution (cases.resolve_par_path)."""
import os

import pytest

from runme import cases


def _touch(path, text="&control\n n_accel = 1\n/\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_existing_path_used_as_is(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    real = tmp_path / "par" / "model.nml"
    _touch(str(real))
    assert cases.resolve_par_path("par/model.nml") == "par/model.nml"


def test_exact_case_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _touch(str(tmp_path / "cases" / "spinup"))
    assert cases.resolve_par_path("spinup") == os.path.join("cases", "spinup")


def test_case_name_without_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _touch(str(tmp_path / "cases" / "spinup.nml"))
    assert cases.resolve_par_path("spinup") == os.path.join("cases", "spinup.nml")


def test_ambiguous_case_name_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _touch(str(tmp_path / "cases" / "spinup.nml"))
    _touch(str(tmp_path / "cases" / "spinup.par"))
    with pytest.raises(FileNotFoundError, match="ambiguous case name"):
        cases.resolve_par_path("spinup")


def test_missing_case_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="not found"):
        cases.resolve_par_path("nope")


def test_real_path_wins_over_case(tmp_path, monkeypatch):
    """A literal path is preferred over a same-named case file."""
    monkeypatch.chdir(tmp_path)
    _touch(str(tmp_path / "spinup"))
    _touch(str(tmp_path / "cases" / "spinup"))
    assert cases.resolve_par_path("spinup") == "spinup"
