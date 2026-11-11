"""Ensemble orchestration for runme.

Given an ensemble parameter set (an :class:`runme.params.XParams`), a dict of
fixed overrides applied to every member, and a resolved run context, this
iterates over the selected members, staging and optionally running/submitting
each.

Output-file layout:

* expdir: ``params.txt`` / ``info.txt``                     -- all params
* expdir: ``params_ensemble.txt`` / ``info_ensemble.txt``   -- permuted subset
* each member rundir: ``params.txt`` / ``info.txt`` (single row, all params)
  plus ``runme.json`` (full record)

``params*.txt`` describe the full ensemble (written once); ``info*.txt`` describe
the members actually processed (honouring the ``-j`` selection). The
``--include-default`` member (fixed params only) is staged under ``default`` and
is not part of the aggregate tables.
"""
import os
import copy
import json
from collections import OrderedDict as odict

from runme import run as _run
from runme import stage as _stage
from runme import hpc as _hpc
from runme.params import str_dataframe


# ---------------------------------------------------------------------------
# Member index selection (slurm sbatch --array syntax)
# ---------------------------------------------------------------------------
def parse_slurm_array_indices(a):
    """Parse ``0,2,4`` or ``0-9:2`` (or a combination) into a list of indices."""
    indices = []
    for i in a.split(","):
        if '-' in i:
            if ':' in i:
                i, step = i.split(':')
                step = int(step)
            else:
                step = 1
            start, stop = i.split('-')
            start = int(start)
            stop = int(stop) + 1  # last index is inclusive
            indices.extend(range(start, stop, step))
        else:
            indices.append(int(i))
    return indices


# ---------------------------------------------------------------------------
# Auto-named run directories (vendored from runner.tools.tree)
# ---------------------------------------------------------------------------
def _short(name, value):
    """Short string representation of a parameter/value for folder names."""
    if isinstance(value, (list, tuple)):
        # vector value: join elements with hyphens (val1-val2-val3)
        value = "-".join("%s" % (v,) for v in value)
    else:
        value = "%s" % (value,)
    if "+" in value:
        value = value.replace('+', '')
    if "/" in value:
        value = value.replace('/', '')
    if ".." in value:
        value = value.replace('..', '')
    if ".nc" in value:
        value = value.replace('.nc', '')

    # name of form "group.param": drop the group
    if "." in name:
        name = name.split(".")[1]

    # remove vowels and underscores from the parameter name
    for letter in ['a', 'e', 'i', 'o', 'u', 'A', 'E', 'I', 'O', 'U', '_']:
        name = name[0] + name[1:].replace(letter, '')

    return ".".join([name, value])


def autofolder(params):
    """Folder name from a list of (name, value) tuples."""
    return '.'.join(_short(*p) for p in params)


def _member_rundir(expdir, runid, names, row, autodir):
    if autodir:
        return os.path.join(expdir, autofolder(list(zip(names, row))))
    return os.path.join(expdir, str(runid))


def _write_table(path, names, rows):
    with open(path, 'w') as f:
        f.write(str_dataframe(list(names), rows) + "\n")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(ctx, xparams, fixed, expdir, indices=None, autodir=False, include_default=False):
    """Run (or stage/submit) an ensemble.

    * ``ctx``      -- run context (see runme.cli.build_context)
    * ``xparams``  -- ensemble parameter matrix (permuted dimensions)
    * ``fixed``    -- dict of fixed overrides applied to every member
    * ``expdir``   -- experiment directory
    * ``indices``  -- members to process (default: all)
    * ``autodir``  -- name run directories from parameter values
    * ``include_default`` -- also run a "default" member with fixed params only
    """
    ens_names = list(xparams.names)
    fixed_names = list(fixed.keys())
    fixed_vals = list(fixed.values())
    all_names = ens_names + fixed_names

    # Write the full-ensemble parameter tables once (describe every member).
    if not ctx.dry_run:
        os.makedirs(expdir, exist_ok=True)
        ens_rows_full = [list(xparams.pset_as_array(i)) for i in range(xparams.size)]
        all_rows_full = [r + fixed_vals for r in ens_rows_full]
        _write_table(os.path.join(expdir, "params.txt"), all_names, all_rows_full)
        _write_table(os.path.join(expdir, "params_ensemble.txt"), ens_names, ens_rows_full)

    if indices is None:
        indices = list(range(xparams.size))

    # A job array: every member is prepared (its own job.submit, for resubmitting
    # it alone), then one array job runs them all.
    array = getattr(ctx, "array", None)
    member_ctx = ctx
    if array is not None:
        member_ctx = copy.copy(ctx)
        member_ctx.run = False
    array_rows = []

    info_rows_all = []
    info_rows_ens = []

    for i in indices:
        ens_row = list(xparams.pset_as_array(i))
        member_params = odict(zip(ens_names, ens_row))
        member_params.update(fixed)

        rundir = _member_rundir(expdir, i, ens_names, ens_row, autodir)
        _run.execute_one(rundir, member_params, member_ctx, create=True)
        array_rows.append((i, rundir))

        if not ctx.dry_run:
            all_row = ens_row + fixed_vals
            _stage.write_run_tables(rundir, all_names, all_row, runid=i)
            label = os.path.basename(os.path.normpath(rundir))
            info_rows_all.append([i] + all_row + [label])
            info_rows_ens.append([i] + ens_row + [label])

    # Optional default member: fixed params only, staged under "default".
    if include_default:
        rundir = os.path.join(expdir, "default")
        _run.execute_one(rundir, odict(fixed), member_ctx, create=True)
        array_rows.append((xparams.size, rundir))   # array index of the default member: one past the last
        if not ctx.dry_run:
            _stage.write_run_tables(rundir, fixed_names, fixed_vals, runid="default")

    # Write the info tables for the processed members.
    if not ctx.dry_run:
        _write_table(os.path.join(expdir, "info.txt"),
                     ["runid"] + all_names + ["rundir"], info_rows_all)
        _write_table(os.path.join(expdir, "info_ensemble.txt"),
                     ["runid"] + ens_names + ["rundir"], info_rows_ens)

    if array is not None and not ctx.dry_run:
        submit_array(ctx, expdir, array_rows, array)

    return


def submit_array(ctx, expdir, rows, limit):
    """Write ``array.submit`` / ``array.dirs`` in ``expdir`` for the prepared
    members ``rows`` (array index, run directory) and, with ``ctx.run``, submit
    it; the job id goes to ``array.json`` and each member's ``runme.json``."""
    expdir_abs = os.path.abspath(expdir)
    per_runid = all(os.path.abspath(d) == os.path.join(expdir_abs, str(i)) for i, d in rows)
    with open(os.path.join(expdir, "array.dirs"), "w") as f:
        for i, d in rows:
            f.write("{} {}\n".format(i, os.path.abspath(d)))
    member_script = _hpc.generate_jobscript(
        ctx.template, ctx.executable, ctx.jobname, ctx.account, ctx.qos, ctx.mem, ctx.wall,
        ctx.partition, ctx.omp, ctx.cpus, ctx.email, ctx.mail_type, ctx.sbatch)
    script = _hpc.generate_array_jobscript(member_script, [i for i, _ in rows], limit, per_runid)
    with open(os.path.join(expdir, "array.submit"), "w") as f:
        f.write(script)
    record = {"ids": _hpc.compress_indices([i for i, _ in rows]), "limit": limit,
              "status": "prepared", "job_id": None}
    if ctx.run:
        out = _hpc.submitjob(expdir, "array.submit")
        job_id = out.split()[-1] if out else None
        record.update(status="submitted", job_id=job_id)
        for i, d in rows:
            _stage.update_record(d, status="submitted", array_job="{}_{}".format(job_id, i))
    with open(os.path.join(expdir, "array.json"), "w") as f:
        json.dump(record, f, indent=2)
    return record
