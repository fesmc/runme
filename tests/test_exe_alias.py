"""Tests for detecting ``par_paths`` that an unaliased executable skips."""
from runme.stage import exe_specific_par_keys


def test_exe_specific_par_keys():
    info = {"par_paths": {"all": ["a.nml"], "climber": ["b.nml"], "": "c.nml"}}
    assert exe_specific_par_keys(info) == ["climber"]


def test_exe_specific_par_keys_generic_only():
    info = {"par_paths": {"all": ["a.nml"], "general": ["b.nml"]}}
    assert exe_specific_par_keys(info) == []
