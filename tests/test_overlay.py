"""Tests for the ``-n`` overlay merge (cli.load_overlay / cli.merge_overlay).

The overlay lets projects that don't take the parameter file as an executable
argument (e.g. climber-x) pass ``-n CASE`` to overlay a partial namelist on top
of the default parameter files, with ``-p`` overrides winning on conflict.
"""
from collections import OrderedDict as odict

from runme.cli import load_overlay, merge_overlay
from runme.namelist import Namelist, param_write_to_files


NML = """\
&control
 n_accel = 1
 tau     = 50
/
"""


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


def test_load_overlay_skipped_when_par_is_argument(tmp_path):
    case = tmp_path / "case.nml"
    _write(str(case), NML)
    info = {"par_path_as_argument": True}
    assert load_overlay(str(case), info) == {}


def test_load_overlay_none_par_path(tmp_path):
    info = {"par_path_as_argument": False}
    assert load_overlay(None, info) == {}


def test_load_overlay_reads_real_group_names(tmp_path):
    case = tmp_path / "case.nml"
    _write(str(case), NML)
    info = {"par_path_as_argument": False}
    overlay = load_overlay(str(case), info)
    assert overlay == {"control.n_accel": 1, "control.tau": 50}


def test_merge_empty_overlay_returns_fixed_unchanged():
    fixed = odict([("ctl.n_accel", 5)])
    assert merge_overlay(odict(), fixed, {"ctl": "control"}) is fixed


def test_merge_normalises_aliases_and_p_wins():
    overlay = odict([("control.n_accel", 1), ("control.tau", 50)])
    fixed = odict([("ctl.tau", 99)])  # -p override using the group alias
    merged = merge_overlay(overlay, fixed, {"ctl": "control"})
    # -p overrides the overlay value despite using the alias group name
    assert merged["control.tau"] == 99
    # untouched overlay parameter survives
    assert merged["control.n_accel"] == 1
    # no divergent alias key left behind
    assert "ctl.tau" not in merged


def test_overlay_lands_in_namelist_file(tmp_path):
    """End-to-end: a merged overlay actually writes into the default par file."""
    src = tmp_path / "default.nml"
    _write(str(src), NML)

    overlay = load_overlay(str(src), {"par_path_as_argument": False})
    overlay["control.tau"] = 200  # simulate a case that bumps tau
    fixed = odict([("ctl.n_accel", 9)])  # -p override on top
    merged = merge_overlay(overlay, fixed, {"ctl": "control"})

    dst = tmp_path / "out.nml"
    param_write_to_files(merged, [str(src)], [str(dst)], {"ctl": "control"})

    result = Namelist().load(open(str(dst)))
    assert result["control.tau"] == 200      # from overlay
    assert result["control.n_accel"] == 9    # from -p
