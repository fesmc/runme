"""Tests for ``par_defaults``: ``-p`` may add a parameter that the staged
parameter file leaves out, as long as a defaults file declares it.
"""
from collections import OrderedDict as odict

import pytest

from runme.config import par_defaults_paths
from runme.namelist import (Namelist, param_write_to_files, group_renames,
                            param_insert, param_coerce)


DEFAULTS = """\
&yelmo
 domain   = "None"
 nml_ydyn = "ydyn"
 nml_ytopo = "ytopo"
/
&ydyn
 ssa_iter_max = 20
 solver = "ssa"
/
&ytopo
 dt_min = 0.1
/
"""

PAR = """\
&ctrl
 time_end = 0.0
/
&yelmo
 domain = "ISLAND4"
/
&ydyn
 solver = "diva"
/
"""

PAR_RENAMED = """\
&ctrl
 time_end = 0.0
/
&yelmo
 domain = "ISLAND4"
 nml_ydyn = "ydyn_north"
/
"""


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)
    return str(path)


def _setup(tmp_path, par=PAR):
    return _write(tmp_path / "defaults.nml", DEFAULTS), _write(tmp_path / "par.nml", par)


def _as_list(v):
    return v if isinstance(v, list) else [v]


def _blocks(path):
    return [line.strip() for line in open(path) if line.startswith("&")]


def test_insert_into_existing_group(tmp_path):
    defaults, par = _setup(tmp_path)
    param_write_to_files({"ydyn.ssa_iter_max": 200}, [par], [par], defaults_paths=[defaults])
    result = Namelist().load(open(par))
    assert result["ydyn.ssa_iter_max"] == 200
    assert result["ydyn.solver"] == "diva"
    assert _blocks(par) == ["&ctrl", "&yelmo", "&ydyn"]


def test_insert_new_group(tmp_path):
    defaults, par = _setup(tmp_path)
    param_write_to_files({"ytopo.dt_min": 0.5}, [par], [par], defaults_paths=[defaults])
    assert Namelist().load(open(par))["ytopo.dt_min"] == 0.5
    assert _blocks(par) == ["&ctrl", "&yelmo", "&ydyn", "&ytopo"]


def test_unknown_key_is_rejected(tmp_path):
    defaults, par = _setup(tmp_path)
    with pytest.raises(Exception, match="ssa_iter_mx"):
        param_write_to_files({"ydyn.ssa_iter_mx": 200}, [par], [par], defaults_paths=[defaults])


def test_driver_group_only_in_par_file(tmp_path):
    defaults, par = _setup(tmp_path)
    param_write_to_files({"ctrl.time_end": 100.0}, [par], [par], defaults_paths=[defaults])
    assert Namelist().load(open(par))["ctrl.time_end"] == 100.0


def test_without_defaults_missing_key_is_rejected(tmp_path):
    _, par = _setup(tmp_path)
    with pytest.raises(Exception, match="not found"):
        param_write_to_files({"ydyn.ssa_iter_max": 200}, [par], [par])


def test_renamed_group_is_checked_against_canonical(tmp_path):
    defaults, par = _setup(tmp_path, PAR_RENAMED)
    param_write_to_files({"ydyn_north.ssa_iter_max": 200}, [par], [par],
                         defaults_paths=[defaults])
    assert Namelist().load(open(par))["ydyn_north.ssa_iter_max"] == 200
    with pytest.raises(Exception, match="ssa_iter_mx"):
        param_write_to_files({"ydyn_north.ssa_iter_mx": 200}, [par], [par],
                             defaults_paths=[defaults])


def test_canonical_name_of_renamed_group_is_rejected(tmp_path):
    defaults, par = _setup(tmp_path, PAR_RENAMED)
    with pytest.raises(Exception, match="renamed to: ydyn_north"):
        param_write_to_files({"ydyn.ssa_iter_max": 200}, [par], [par],
                             defaults_paths=[defaults])


def test_group_renames():
    defaults = Namelist().loads(DEFAULTS)
    sources = [odict([("yelmo_n.nml_ydyn", "ydyn_n")]),
               odict([("yelmo_s.nml_ydyn", "ydyn"), ("yelmo_s.nml_ytopo", "ytopo_s")])]
    renames, renamed = group_renames(defaults, sources)
    assert renames == {"ydyn_n": "ydyn", "ytopo_s": "ytopo"}
    assert renamed == {"ytopo"}


def test_vector_value_inserted(tmp_path):
    defaults, par = _setup(tmp_path)
    param_write_to_files({"ytopo.dt_min": [1, 2, 3]}, [par], [par], defaults_paths=[defaults])
    assert Namelist().load(open(par))["ytopo.dt_min"] == [1, 2, 3]


def test_new_key_goes_to_file_holding_group(tmp_path):
    defaults = _write(tmp_path / "defaults.nml", DEFAULTS)
    a = _write(tmp_path / "a.nml", "&ctrl\n time_end = 0.0\n/\n")
    b = _write(tmp_path / "b.nml", "&ydyn\n solver = 'ssa'\n/\n")
    param_write_to_files({"ydyn.ssa_iter_max": 5}, [a, b], [a, b], defaults_paths=[defaults])
    assert "ydyn.ssa_iter_max" not in Namelist().load(open(a))
    assert Namelist().load(open(b))["ydyn.ssa_iter_max"] == 5


def test_new_group_with_several_files_is_ambiguous(tmp_path):
    defaults = _write(tmp_path / "defaults.nml", DEFAULTS)
    a = _write(tmp_path / "a.nml", "&ctrl\n time_end = 0.0\n/\n")
    b = _write(tmp_path / "b.nml", "&ydyn\n solver = 'ssa'\n/\n")
    with pytest.raises(Exception, match="cannot choose"):
        param_write_to_files({"ytopo.dt_min": 1.0}, [a, b], [a, b], defaults_paths=[defaults])


def test_param_insert_keeps_groups_contiguous():
    params = odict([("a.x", 1), ("b.y", 2), ("a.z", 3)])
    out = param_insert(params, odict([("a.w", 4), ("c.v", 5)]))
    assert list(out) == ["a.x", "b.y", "a.z", "a.w", "c.v"]


def test_par_defaults_paths():
    assert par_defaults_paths({}) == []
    assert par_defaults_paths({"par_defaults": "d.nml"}) == ["d.nml"]
    assert par_defaults_paths({"par_defaults": ["d.nml", "e.nml"]}) == ["d.nml", "e.nml"]


# ---------------------------------------------------------------------------
# Values take the type of the parameter's current value
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("True", True), (".true.", True), ("T", True), ("t", True),
    ("False", False), (".false.", False), ("F", False),
])
def test_logical_values(tmp_path, raw, expected):
    par = _write(tmp_path / "par.nml", "&g\n flag = .false.\n/\n")
    param_write_to_files({"g.flag": raw}, [par], [par])
    text = open(par).read()
    assert (".true." if expected else ".false.") in text
    assert "'" not in text
    assert Namelist().load(open(par))["g.flag"] is expected


def test_logical_value_inserted_from_defaults(tmp_path):
    defaults = _write(tmp_path / "defaults.nml", "&g\n flag = .false.\n/\n")
    par = _write(tmp_path / "par.nml", "&h\n x = 1\n/\n")
    param_write_to_files({"g.flag": "T"}, [par], [par], defaults_paths=[defaults])
    assert Namelist().load(open(par))["g.flag"] is True


@pytest.mark.parametrize("value,ref,expected", [
    (10, 1.0, 10.0),            # integer -> real
    (16, "x", "16"),            # number -> string
    (2.5, 1, 2.5),              # real stays real for an integer parameter
    ("abc", 1.0, "abc"),        # unconvertible values pass through
    ("yes", False, "yes"),
    ([1, 2], [1.0], [1.0, 2.0]),  # vectors item by item
    (["T", "F"], [False], [True, False]),
    ([1, 2], 1.0, [1.0, 2.0]),  # scalar reference for a vector value
])
def test_param_coerce(value, ref, expected):
    out = param_coerce(value, ref)
    assert out == expected
    assert [type(v) for v in _as_list(out)] == [type(v) for v in _as_list(expected)]
