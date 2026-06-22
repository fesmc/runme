"""Tests for parameter-file formats and extension dispatch (runme.filetype)."""
from collections import OrderedDict as odict

import pytest

from runme.filetype import Json, LineSep, Toml, filetype_for_path
from runme.namelist import Namelist, param_write_to_files


TOML = """\
[control]
n_accel = 1
tau = 50.0
name = "spinup"
on = true
windows = [10, 20, 30]
"""


def test_toml_round_trips_to_group_name_dict():
    params = Toml().loads(TOML)
    assert params == odict([
        ("control.n_accel", 1),
        ("control.tau", 50.0),
        ("control.name", "spinup"),
        ("control.on", True),
        ("control.windows", [10, 20, 30]),
    ])


def test_toml_dumps_reloads_identically():
    params = Toml().loads(TOML)
    assert Toml().loads(Toml().dumps(params)) == params


def test_toml_dumps_emits_tables():
    params = odict([("control.tau", 50.0), ("control.on", False),
                    ("io.path", "out/")])
    out = Toml().dumps(params)
    assert "[control]" in out
    assert "tau = 50.0" in out
    assert "on = false" in out
    assert 'path = "out/"' in out
    # a blank line separates the two tables
    assert "[io]" in out


def test_toml_nested_table_is_an_error():
    with pytest.raises(ValueError):
        Toml().loads("[control]\n[control.sub]\ntau = 1.0\n")


def test_toml_bare_top_level_key_is_an_error():
    with pytest.raises(ValueError):
        Toml().loads("tau = 1.0\n")


JSON = """\
{
  "control": {
    "n_accel": 1,
    "tau": 50.0,
    "name": "spinup",
    "on": true,
    "windows": [10, 20, 30]
  }
}
"""


def test_json_round_trips_to_group_name_dict():
    params = Json().loads(JSON)
    assert params == odict([
        ("control.n_accel", 1),
        ("control.tau", 50.0),
        ("control.name", "spinup"),
        ("control.on", True),
        ("control.windows", [10, 20, 30]),
    ])


def test_json_dumps_reloads_identically():
    params = Json().loads(JSON)
    assert Json().loads(Json().dumps(params)) == params


def test_json_dumps_nests_by_group():
    params = odict([("control.tau", 50.0), ("io.path", "out/")])
    assert Json().loads(Json().dumps(params)) == params


def test_json_nested_object_is_an_error():
    with pytest.raises(ValueError):
        Json().loads('{"control": {"sub": {"tau": 1.0}}}')


def test_json_bare_top_level_key_is_an_error():
    with pytest.raises(ValueError):
        Json().loads('{"tau": 1.0}')


JL = """\
# a saved case
control.n_accel = 1
control.tau     = 50.0
control.name    = "spinup"
control.on      = true
control.windows = [10, 20, 30]
io.path         = "out/"   # trailing comment
"""


def test_jl_round_trips_to_group_name_dict():
    params = LineSep().loads(JL)
    assert params == odict([
        ("control.n_accel", 1),
        ("control.tau", 50.0),
        ("control.name", "spinup"),
        ("control.on", True),
        ("control.windows", [10, 20, 30]),
        ("io.path", "out/"),
    ])


def test_jl_dumps_uses_equals_and_julia_literals():
    params = odict([("control.tau", 50.0), ("control.on", False),
                    ("control.name", "spin"), ("control.windows", [1, 2]),
                    ("io.path", "out/")])
    out = LineSep().dumps(params)
    assert "control.tau = 50.0" in out
    assert "control.on = false" in out          # not Fortran .false.
    assert 'control.name = "spin"' in out       # double-quoted, not 'spin'
    assert "control.windows = [1, 2]" in out
    assert 'io.path = "out/"' in out


def test_jl_dumps_reloads_identically():
    params = LineSep().loads(JL)
    assert LineSep().loads(LineSep().dumps(params)) == params


def test_jl_key_without_group_is_an_error():
    with pytest.raises(ValueError):
        LineSep().loads("tau = 50.0\n")


def test_jl_deeper_nesting_key_is_an_error():
    with pytest.raises(ValueError):
        LineSep().loads("control.sub.tau = 1.0\n")


def test_filetype_for_path_dispatches_on_extension():
    assert isinstance(filetype_for_path("a/b/p.toml"), Toml)
    assert isinstance(filetype_for_path("a/b/p.json"), Json)
    assert isinstance(filetype_for_path("a/b/p.jl"), LineSep)
    assert isinstance(filetype_for_path("a/b/p.nml"), Namelist)
    assert isinstance(filetype_for_path("a/b/p.par"), Namelist)


def test_filetype_for_path_rejects_unknown_extension():
    with pytest.raises(ValueError):
        filetype_for_path("a/b/p.yaml")


def test_param_write_updates_toml_file(tmp_path):
    src = tmp_path / "default.toml"
    src.write_text(TOML)
    dst = tmp_path / "out.toml"

    param_write_to_files({"control.tau": 99.0}, [str(src)], [str(dst)])

    result = Toml().load(open(str(dst)))
    assert result["control.tau"] == 99.0     # overridden
    assert result["control.n_accel"] == 1    # untouched


def test_param_write_converts_namelist_to_toml(tmp_path):
    """Source and destination formats may differ: read namelist, write TOML."""
    src = tmp_path / "default.nml"
    src.write_text("&control\n tau = 50\n/\n")
    dst = tmp_path / "out.toml"

    param_write_to_files({"control.tau": 7}, [str(src)], [str(dst)])

    assert Toml().load(open(str(dst)))["control.tau"] == 7


def test_param_write_updates_json_file(tmp_path):
    src = tmp_path / "default.json"
    src.write_text(JSON)
    dst = tmp_path / "out.json"

    param_write_to_files({"control.tau": 99.0}, [str(src)], [str(dst)])

    result = Json().load(open(str(dst)))
    assert result["control.tau"] == 99.0     # overridden
    assert result["control.n_accel"] == 1    # untouched


def test_param_write_converts_namelist_to_jl(tmp_path):
    """Read namelist, write the Julia-assignment line format."""
    src = tmp_path / "default.nml"
    src.write_text("&control\n tau = 50\n name = 'spinup'\n/\n")
    dst = tmp_path / "out.jl"

    param_write_to_files({"control.tau": 7}, [str(src)], [str(dst)])

    text = dst.read_text()
    assert "control.tau = 7" in text
    assert 'control.name = "spinup"' in text     # namelist quotes -> Julia quotes
    assert LineSep().load(open(str(dst)))["control.tau"] == 7


def test_restage_preserves_runme_json_record(tmp_path):
    """The cleanup glob now matches ``*.json`` but must keep the run record."""
    from runme.stage import RECORD, makedirs

    rundir = tmp_path / "run"
    rundir.mkdir()
    (rundir / RECORD).write_text("{}")
    (rundir / "model.json").write_text('{"control": {"tau": 1.0}}')
    (rundir / "params.nml").write_text("&control\n tau = 1\n/\n")

    makedirs(str(rundir), remove=True)

    assert (rundir / RECORD).exists()              # record preserved
    assert not (rundir / "model.json").exists()    # stale param file cleared
    assert not (rundir / "params.nml").exists()
