"""Saved parameter "cases".

A case is just a normal (partial or complete) parameter file kept in the
project's ``cases/`` folder, in any supported format (``.nml``/``.par``
namelist, ``.toml``, ``.json``, or ``.jl``). It is used via ``-n``: pass a path
as usual, or pass a bare case name and runme will look it up under ``cases/``.

This module provides the ``-n`` name resolution (:func:`resolve_par_path`).
"""
import os
import glob
import json

# Folder searched when ``-n NAME`` is not an existing path.
CASES_DIR = "cases"

# Per-rundir record written by runme.stage (kept in sync with stage.RECORD).
RECORD = "runme.json"


def resolve_par_path(par_path):
    """Resolve a ``-n`` value to a parameter-file path.

    Resolution order:

    1. ``par_path`` as given, if it exists (a real relative/absolute path);
    2. ``cases/<par_path>``, if it exists (case used by exact name);
    3. ``cases/<par_path>.*``, if exactly one file matches (case used by name
       without its extension).

    A name that matches nothing, or that matches more than one ``cases/<name>.*``
    file, raises ``FileNotFoundError`` with a message listing what was tried.
    """
    if os.path.exists(par_path):
        return par_path

    exact = os.path.join(CASES_DIR, par_path)
    if os.path.exists(exact):
        print("Using case: {}".format(exact))
        return exact

    matches = sorted(glob.glob(os.path.join(CASES_DIR, par_path + ".*")))
    if len(matches) == 1:
        print("Using case: {}".format(matches[0]))
        return matches[0]
    if len(matches) > 1:
        raise FileNotFoundError(
            "ambiguous case name '{}': multiple files match {}:\n  {}".format(
                par_path, os.path.join(CASES_DIR, par_path + ".*"),
                "\n  ".join(matches)))

    raise FileNotFoundError(
        "parameter file not found: '{}' is neither an existing path nor a case "
        "in {}/ (looked for {}, {} and {}.*).".format(
            par_path, CASES_DIR, par_path, exact, exact))


def save_case(name, rundir, grp_aliases=None):
    """Save the parameters applied in ``rundir`` as a case file under ``cases/``.

    Reads the run's record (``runme.json``) and writes its applied parameters as
    a partial parameter file to ``cases/<name>``, in the format implied by the
    extension (a ``.nml`` extension is added when ``name`` has none). Group
    aliases are normalised to their real group names so the saved file is a
    valid standalone parameter file. Works for any run directory that has a
    record with applied parameters, including an ensemble member.
    """
    record_path = os.path.join(rundir, RECORD)
    if not os.path.isfile(record_path):
        raise FileNotFoundError(
            "no {} in '{}' — not a runme run directory.".format(RECORD, rundir))

    with open(record_path) as f:
        params = json.load(f).get("params") or {}
    if not params:
        raise ValueError(
            "run '{}' has no applied parameters to save as a case.".format(rundir))

    if grp_aliases:
        from runme.namelist import param_map_groups
        params = param_map_groups(params, grp_aliases)

    from runme.filetype import filetype_for_path
    os.makedirs(CASES_DIR, exist_ok=True)
    if os.path.splitext(name)[1] == "":
        name = name + ".nml"
    dest = os.path.join(CASES_DIR, name)
    with open(dest, "w") as f:
        filetype_for_path(dest).dump(params, f)
    print("Saved case: {}".format(dest))
    return dest
