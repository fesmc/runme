"""Run-directory staging for runme.

Creates and populates a run directory ready for execution, and writes the
per-rundir ``runme.json`` record. Shared by the single-simulation path and (in
Phase 4) the ensemble path so every run directory is self-describing.

The human-readable ``params.txt`` / ``info.txt`` text tables are added in
Phase 4 (their writer is shared with the ensemble aggregate files).
"""
import os
import sys
import glob
import json
import shutil
import datetime
import subprocess as subp
from itertools import chain

from runme import __version__
from runme.namelist import param_write_to_files

# Record file written into every run directory.
RECORD = "runme.json"

# Keys in info["par_paths"] that apply regardless of the chosen executable.
GENERIC_PAR_KEYS = {"", "all", "none", "na", "general"}


def stage_rundir(rundir, info, exe_path, exe_alias, par_path=None, params=None,
                 grp_aliases=None, create=True):
    """Populate ``rundir`` ready to run.

    Steps: (optionally) create the directory, copy extra files and special
    directories, create input-data symlinks, copy the executable, copy the
    relevant parameter files, then apply any ``-p`` parameter overrides to the
    namelists in the run directory.

    Returns the list of parameter-file paths inside ``rundir``.
    """
    if create:
        makedirs(rundir, remove=True)

    # Copy files as needed
    copy_files(info["files"], rundir)

    # Copy special dirs that need a different destination
    for src, dst in info["dir-special"].items():
        copy_dir(src, rundir, dst)

    # Generate symbolic links to input data folders
    for link in info["links"]:
        make_link(link, rundir)

    # Copy exe file to rundir (even if running from cwd)
    shutil.copy(exe_path, rundir)

    # Build the list of parameter files relevant to this executable: generic
    # keys plus the chosen executable alias. Each entry may be a single path or
    # a list of paths.
    allowed_keys = GENERIC_PAR_KEYS | {exe_alias}
    par_paths = list(chain.from_iterable(
        [v] if isinstance(v, str) else v
        for k, v in info["par_paths"].items() if k in allowed_keys
    ))

    if info["par_path_as_argument"] is True and par_path is not None:
        par_paths.append(par_path)  # included parameter file provided at command line

    # Eliminate empty entries
    par_paths = [entry for entry in par_paths if entry and entry != "None"]

    # Copy the default parameter files to the rundir
    copy_files(par_paths, rundir)

    # List of new parameter-file destinations
    par_paths_rundir = []
    for path in par_paths:
        par_paths_rundir.append(os.path.join(rundir, os.path.basename(path)))

    # Apply command-line parameter overrides (-p key=val ...) in the rundir
    if params:
        param_write_to_files(params, par_paths_rundir, par_paths_rundir, grp_aliases)

    return par_paths_rundir


def write_record(rundir, params, command, exe_command, status):
    """Write the per-rundir ``runme.json`` record.

    Captures the invocation, the executable command, the applied parameters, the
    git revision, and a status. Replaces the old ``run_info.txt``.
    """
    record = {
        "command": command,           # the runme invocation (sys.argv)
        "exe_command": exe_command,   # the model executable command line
        "params": params or {},
        "rundir": rundir,
        "git_hash": get_git_revision_hash() if os.path.isdir(".git") else "Not under git version control.",
        "time": str(datetime.datetime.now()),
        "runme_version": __version__,
        "status": status,
    }

    with open(os.path.join(rundir, RECORD), 'w') as f:
        json.dump(record, f, indent=2)

    return record


# ---------------------------------------------------------------------------
# File / directory helpers
# ---------------------------------------------------------------------------

def make_link(srcname, rundir, target=None):
    """Make a symlink in the run directory."""
    if target is None:
        target = srcname

    dstname = os.path.join(rundir, target)
    if os.path.islink(dstname):
        os.unlink(dstname)

    if os.path.islink(srcname):
        linkto = os.readlink(srcname)
        os.symlink(linkto, dstname)
    elif os.path.isdir(srcname):
        srcpath = os.path.abspath(srcname)
        os.symlink(srcpath, dstname)
    else:
        print("Warning: path does not exist {}".format(srcname))

    return


def copy_dir(path, rundir, target):
    """Copy a directory tree into the run directory under ``target``."""
    if not path == "" and not path == "None":
        dst = os.path.join(rundir, target)
        shutil.copytree(path, dst, dirs_exist_ok=True)  # 3.8+

    return


def copy_file(path, rundir, target):
    """Copy a single file into the run directory under ``target``."""
    if not path == "" and not path == "None":
        dst = os.path.join(rundir, target)
        shutil.copy(path, dst)

    return


def copy_files(paths, rundir):
    """Bulk-copy files into the run directory."""
    for pnow in paths:
        if not pnow == "" and not pnow == "None":
            shutil.copy(pnow, rundir)

    return


def makedirs(dirname, remove):
    """Create a directory (and parents).

    If it already exists and ``remove`` is set, clear stale ``*.nc`` / ``*.nml``
    files from it.
    """
    try:
        os.makedirs(dirname)
        print('Directory created: {}'.format(dirname))
    except OSError:
        if os.path.isdir(dirname):
            print('Directory already exists: {}'.format(dirname))
            if remove:
                for f in glob.glob("{}/*.nc".format(dirname)):
                    os.remove(f)
                for f in glob.glob("{}/*.nml".format(dirname)):
                    os.remove(f)
        else:
            # There was an error on creation, so make sure we know about it
            raise

    return


def get_git_revision_hash():
    githash = subp.check_output(['git', 'rev-parse', 'HEAD']).strip()
    return githash.decode("ascii")
