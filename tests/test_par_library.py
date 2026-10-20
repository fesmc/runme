"""Tests for ``par_library``: ``-p`` on a group the staged parameter file lacks
copies the whole group from a library file, then applies the override.
"""
import os
from argparse import Namespace

import pytest

from runme import ensemble as _ensemble
from runme.config import par_library_paths
from runme.namelist import Namelist, param_write_to_files
from runme.params import MultiParam, Param
from runme.stage import stage_rundir


LIBRARY = """\
&idx_a
 f_min = 0.5
 f_max = 1.0
 file  = "idx_a.nc"
/
&snap_lgm
 dT = -6.0
/
"""

LIBRARY_2 = """\
&idx_a
 f_min = 9.0
/
&idx_b
 f_min = 0.2
/
"""

DEFAULTS = """\
&idx_a
 f_min = 0.0
 f_extra = 1.0
/
&ytopo
 dt_min = 0.1
/
"""

PAR = """\
&ctrl
 time_end = 0.0
/
&idx_a
 f_min = 0.1
/
"""


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)
    return str(path)


def _load(path):
    return Namelist().load(open(path))


def _blocks(path):
    return [line.strip() for line in open(path) if line.startswith("&")]


def test_group_copied_whole_and_override_applied(tmp_path, capsys):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    param_write_to_files({"idx_a.f_min": 0}, [par], [par], library_paths=[lib])
    result = _load(par)
    assert [k for k in result if k.startswith("idx_a.")] == \
        ["idx_a.f_min", "idx_a.f_max", "idx_a.file"]
    assert result["idx_a.f_min"] == 0.0
    assert result["idx_a.f_max"] == 1.0
    assert result["idx_a.file"] == "idx_a.nc"
    assert "snap_lgm.dT" not in result
    assert _blocks(par) == ["&ctrl", "&idx_a"]
    assert "Copied group &idx_a from {}".format(lib) in capsys.readouterr().out


def test_group_in_par_file_does_not_touch_library(tmp_path, capsys):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    par = _write(tmp_path / "par.nml", PAR)
    param_write_to_files({"idx_a.f_min": 0.3}, [par], [par], library_paths=[lib])
    result = _load(par)
    assert result["idx_a.f_min"] == 0.3
    assert "idx_a.f_max" not in result
    assert "Copied group" not in capsys.readouterr().out
    with pytest.raises(Exception, match="f_max"):
        param_write_to_files({"idx_a.f_max": 2.0}, [par], [par], library_paths=[lib])


def test_unknown_key_in_library_group_is_rejected(tmp_path):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    defaults = _write(tmp_path / "defaults.nml", DEFAULTS)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    # f_extra is declared in the defaults, but the library group wins
    with pytest.raises(Exception, match="f_extra") as err:
        param_write_to_files({"idx_a.f_extra": 2.0}, [par], [par],
                             defaults_paths=[defaults], library_paths=[lib])
    assert lib in str(err.value)
    assert "idx_a" not in open(par).read()


def test_first_library_file_holding_group_wins(tmp_path):
    lib1 = _write(tmp_path / "lib1.nml", LIBRARY)
    lib2 = _write(tmp_path / "lib2.nml", LIBRARY_2)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    param_write_to_files({"idx_a.f_max": 2.0, "idx_b.f_min": 0.4}, [par], [par],
                         library_paths=[lib1, lib2])
    result = _load(par)
    assert result["idx_a.f_min"] == 0.5
    assert result["idx_a.f_max"] == 2.0
    assert result["idx_b.f_min"] == 0.4
    assert _blocks(par) == ["&ctrl", "&idx_a", "&idx_b"]


def test_absent_from_library_falls_back_to_defaults(tmp_path):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    defaults = _write(tmp_path / "defaults.nml", DEFAULTS)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    param_write_to_files({"ytopo.dt_min": 0.5}, [par], [par],
                         defaults_paths=[defaults], library_paths=[lib])
    result = _load(par)
    assert result["ytopo.dt_min"] == 0.5
    assert not any(k.startswith("idx_a.") for k in result)


def test_missing_everywhere_lists_library(tmp_path):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    with pytest.raises(Exception, match="not found") as err:
        param_write_to_files({"nogroup.x": 1}, [par], [par], library_paths=[lib])
    assert lib in str(err.value)


def test_grp_aliases_resolved(tmp_path):
    lib = _write(tmp_path / "lib.nml", LIBRARY)
    par = _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    param_write_to_files({"ia.f_min": 0}, [par], [par], grp_aliases={"ia": "idx_a"},
                         library_paths=[lib])
    result = _load(par)
    assert result["idx_a.f_min"] == 0.0
    assert result["idx_a.f_max"] == 1.0


def test_ensemble_members_each_get_group(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "lib.nml", LIBRARY)
    _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    _write(tmp_path / "model.x", "")
    info = {"par_paths": {"": "par.nml"}, "par_path_as_argument": False,
            "files": [], "dir-special": {}, "links": [], "grp_aliases": {},
            "par_library": ["lib.nml"]}
    ctx = Namespace(dry_run=False, submit=False, run=False, info=info,
                    exe_path="model.x", exe_alias=None, par_path=None,
                    command=["runme"], executable="./model.x")
    xparams = MultiParam([Param.parse("idx_a.f_min=0,0.2")]).product()
    _ensemble.run(ctx, xparams, {"ctrl.time_end": 10.0}, "ens")
    for i, f_min in enumerate([0.0, 0.2]):
        result = _load(os.path.join("ens", str(i), "par.nml"))
        assert result["idx_a.f_min"] == f_min
        assert result["idx_a.f_max"] == 1.0
        assert result["ctrl.time_end"] == 10.0


def _stage(tmp_path, par_paths, par_path=None, params=None):
    _write(tmp_path / "lib.nml", LIBRARY)
    _write(tmp_path / "model.x", "")
    info = {"par_paths": {"": par_paths}, "par_path_as_argument": par_path is not None,
            "files": [], "dir-special": {}, "links": [], "par_library": ["lib.nml"]}
    return stage_rundir("run", info, "model.x", None, par_path=par_path, params=params)


def test_new_group_goes_into_n_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "base.nml", "&ctrl\n time_end = 0.0\n/\n")
    _write(tmp_path / "case.nml", "&yelmo\n domain = 'GRL'\n/\n")
    _stage(tmp_path, "base.nml", par_path="case.nml",
           params={"snap_lgm.dT": -4.0, "ctrl.time_end": 10.0})
    base = _load(os.path.join("run", "base.nml"))
    case = _load(os.path.join("run", "case.nml"))
    assert case["snap_lgm.dT"] == -4.0
    assert _blocks(os.path.join("run", "case.nml")) == ["&yelmo", "&snap_lgm"]
    assert not any(k.startswith("snap_lgm.") for k in base)
    assert base["ctrl.time_end"] == 10.0


def test_new_group_without_n_file_is_ambiguous(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "base.nml", "&ctrl\n time_end = 0.0\n/\n")
    _write(tmp_path / "case.nml", "&yelmo\n domain = 'GRL'\n/\n")
    with pytest.raises(Exception, match="cannot choose"):
        _stage(tmp_path, ["base.nml", "case.nml"], params={"snap_lgm.dT": -4.0})


def test_new_group_single_file_staged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "par.nml", "&ctrl\n time_end = 0.0\n/\n")
    _stage(tmp_path, "par.nml", params={"snap_lgm.dT": -4.0})
    assert _load(os.path.join("run", "par.nml"))["snap_lgm.dT"] == -4.0


def test_par_library_paths():
    assert par_library_paths({}) == []
    assert par_library_paths({"par_library": "l.nml"}) == ["l.nml"]
    assert par_library_paths({"par_library": ["l.nml", "m.nml"]}) == ["l.nml", "m.nml"]
