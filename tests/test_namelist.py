"""Tests for the namelist parser: quoted strings are opaque to the syntax."""
import pytest

from runme.namelist import Namelist, parse_nml


def test_ampersand_in_string_keeps_group():
    s = '''&ctrl
    time_end = 100.0
/
&yelmo_masks
    mask_ice_dynamic = "region:Greenland,Canadian_Arctic_Archipelago"
    mask_rmse        = "region:Greenland & ~zone:open_ocean"
/
'''
    p = Namelist().loads(s)
    assert p["ctrl.time_end"] == 100.0
    assert p["yelmo_masks.mask_ice_dynamic"] == "region:Greenland,Canadian_Arctic_Archipelago"
    assert p["yelmo_masks.mask_rmse"] == "region:Greenland & ~zone:open_ocean"


def test_slash_before_ampersand_in_strings():
    s = '''&marine_shelf
    path           = "ice_data/v2/ANT-32KM_REGIONS.nc"
    mask_pico_deep = "region:Antarctica & zone:shelf_break_buffer"
/
'''
    p = Namelist().loads(s)
    assert p["marine_shelf.path"] == "ice_data/v2/ANT-32KM_REGIONS.nc"
    assert p["marine_shelf.mask_pico_deep"] == "region:Antarctica & zone:shelf_break_buffer"


def test_bang_and_equals_in_string_with_comment():
    s = '''&g
    expr = 'a != b & !c'   ! the comment / with & syntax
    eq   = "x=1"
/
'''
    params = parse_nml(s)
    assert [(q.name, q.value, q.help) for q in params] == [
        ("expr", "a != b & !c", "the comment / with & syntax"),
        ("eq", "x=1", ""),
    ]


def test_string_arrays_and_doubled_quotes():
    s = '''&g
    names = "a,b", 'c d', "e"
    rep   = 2*"x,y"
    apos  = 'it''s'
/
'''
    p = Namelist().loads(s)
    assert p["g.names"] == ["a,b", "c d", "e"]
    assert p["g.rep"] == ["x,y", "x,y"]
    assert p["g.apos"] == "it's"


def test_continuation_lines_and_single_line_group():
    s = '''&g
    v = 1, 2,
        3, 4
/
&h a = 1 /
'''
    p = Namelist().loads(s)
    assert p["g.v"] == [1, 2, 3, 4]
    assert p["h.a"] == 1


def test_unclosed_group_raises():
    with pytest.raises(ValueError):
        parse_nml("&g\n a = 1\n")


def test_round_trip():
    s = '''&g
    path = "a/b/c.nc"
    expr = "region:X & ~zone:Y"
    note = "keep ! this"
    flag = .true.
    v    = 1.0 2.0
/
'''
    nml = Namelist()
    p = nml.loads(s)
    assert nml.loads(nml.dumps(p)) == p


def test_group_name_with_dash_and_dot():
    p = Namelist().loads("&Atl_50-70N_0.1Sv\n a = 1\n/\n&NH-80KM\n b = 2\n/\n")
    assert p == {"Atl_50-70N_0.1Sv.a": 1, "NH-80KM.b": 2}
