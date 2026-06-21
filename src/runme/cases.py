"""Saved parameter "cases".

A case is just a normal (partial or complete) namelist parameter file kept in
the project's ``cases/`` folder. It is used via ``-n``: pass a path as usual, or
pass a bare case name and runme will look it up under ``cases/``.

This module provides the ``-n`` name resolution (:func:`resolve_par_path`).
"""
import os
import glob

# Folder searched when ``-n NAME`` is not an existing path.
CASES_DIR = "cases"


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
