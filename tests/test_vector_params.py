"""Tests for vector ``-p`` values (``[..]`` bracket syntax) and their
round-trip through the fixed-width ensemble tables."""
import os
from collections import OrderedDict as odict

from runme.cli import _is_ensemble_spec, _coerce, classify_params
from runme.dist import split_top_level, parse_val
from runme.params import (MultiParam, Param, XParams,
                          str_dataframe, read_dataframe)


# --- classification: what is a vector vs. an ensemble dimension --------------
def test_bracket_value_is_a_fixed_override_not_an_ensemble():
    assert not _is_ensemble_spec("[1,2,3]")
    assert _coerce("[1,2,3]") == [1, 2, 3]


def test_list_of_vectors_is_an_ensemble_dimension():
    assert _is_ensemble_spec("[1,2],[3,4]")


def test_plain_comma_list_stays_an_ensemble_dimension():
    assert _is_ensemble_spec("1,2,3")


def test_scalar_and_range_and_dist_unchanged():
    assert not _is_ensemble_spec("5")
    assert _coerce("5") == 5
    assert _is_ensemble_spec("0:10:5")
    assert _is_ensemble_spec("U?0,1")


def test_classify_params_splits_vectors_and_ensembles():
    specs, fixed = classify_params(["a=1,2", "g.par=[1,2],[3,4]", "g.c=[9,9]"])
    assert specs == ["a=1,2", "g.par=[1,2],[3,4]"]
    assert fixed == odict([("g.c", [9, 9])])


# --- low-level helpers -------------------------------------------------------
def test_split_top_level_ignores_bracketed_commas():
    assert split_top_level("[1,2],[3,4]", ",") == ["[1,2]", "[3,4]"]
    assert split_top_level("[1,2,3]", ",") == ["[1,2,3]"]
    assert split_top_level("1,2,3", ",") == ["1", "2", "3"]


def test_parse_val_parses_bracket_literal():
    assert parse_val("[1,2,3]") == [1, 2, 3]
    assert parse_val("[1.5, 2.0]") == [1.5, 2.0]
    assert parse_val("[]") == []
    assert parse_val("5") == 5


# --- ensemble expansion over vectors ----------------------------------------
def test_product_expands_over_vector_values():
    specs = ["a=1,2", "g.par=[1,2],[3,4]"]
    xp = MultiParam([Param.parse(s) for s in specs]).product()
    rows = [list(xp.pset_as_array(i)) for i in range(xp.size)]
    assert rows == [[1, [1, 2]], [1, [3, 4]], [2, [1, 2]], [2, [3, 4]]]


def test_product_tolerates_ragged_vector_lengths():
    xp = MultiParam([Param.parse("g.par=[1,2],[3,4,5]")]).product()
    rows = [list(xp.pset_as_array(i)) for i in range(xp.size)]
    assert rows == [[[1, 2]], [[3, 4, 5]]]


# --- fixed-width table round-trip -------------------------------------------
def test_vector_table_round_trips(tmp_path):
    names = ["a", "g.par"]
    rows = [[1, [1, 2]], [1, [3, 4]], [2, [1, 2]], [2, [3, 4]]]
    tbl = str_dataframe(names, rows)
    # vector cells are written space-free so the columns stay tokenizable
    assert "[1,2]" in tbl and "[1, 2]" not in tbl

    p = os.path.join(str(tmp_path), "params.txt")
    with open(p, "w") as f:
        f.write(tbl + "\n")
    read_names, read_rows = read_dataframe(p)
    assert read_names == names
    assert read_rows == rows


def test_xparams_read_recovers_vector_columns(tmp_path):
    names = ["a", "g.par"]
    rows = [[1, [1, 2]], [2, [3, 4]]]
    p = os.path.join(str(tmp_path), "params.txt")
    with open(p, "w") as f:
        f.write(str_dataframe(names, rows) + "\n")
    xp = XParams.read(p)
    assert [list(xp.pset_as_array(i)) for i in range(xp.size)] == rows
