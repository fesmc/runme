"""Execute a single staged simulation.

Shared by the single-simulation path (:mod:`runme.cli`) and the ensemble path
(:mod:`runme.ensemble`), so one run directory is staged, run/submitted, and
recorded the same way regardless of how it was produced.

The member-independent context (resolved executable, queue settings, flags) is
carried in a plain ``argparse.Namespace`` built by :func:`runme.cli.build_context`.
"""
import json
import os
import sys

from runme import stage as _stage
from runme import hpc as _hpc


def active_job(rundir):
    """The job recorded in ``rundir``'s ``runme.json`` (``job_id``, or ``array_job``
    of an array member) and its Slurm state, if it is still queued or running;
    else None."""
    try:
        with open(os.path.join(rundir, _stage.RECORD)) as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    job = record.get("job_id") or record.get("array_job")
    if not job:
        return None
    state = _hpc.queued_state(job)
    return (job, state) if state else None


def check_free(rundirs):
    """Stop, before anything is staged or submitted, if any of ``rundirs`` holds a
    job that is still queued or running: a second run there would overwrite its
    files while it writes them."""
    busy = [(d,) + a for d in rundirs for a in [active_job(d)] if a]
    if busy:
        lines = ["  {}: job {} ({})".format(d, job, state) for d, job, state in busy]
        sys.exit("error: run directories with a job still in the queue:\n{}\nNothing was staged "
                 "or submitted. Wait for the jobs, cancel them (scancel), or use other "
                 "directories.".format("\n".join(lines)))


def execute_one(rundir, params, ctx, create=True, check=True):
    """Stage ``rundir`` with ``params`` and run/submit it per ``ctx``.

    Unless ``check`` is False (the caller checked already), stops first if
    ``rundir`` holds a job still in the queue (``check_free``).

    Returns the run status: one of ``staged``, ``prepared``, ``running``,
    ``submitted``, or ``dry-run``.
    """
    if ctx.dry_run:
        print("[dry-run] {}".format(rundir))
        print("          command: {}".format(ctx.executable))
        print("          params : {}".format(dict(params or {})))
        return "dry-run"

    if check:
        check_free([rundir])

    # 1. Populate the run directory.
    _stage.stage_rundir(rundir, ctx.info, ctx.exe_path, ctx.exe_alias,
                        par_path=ctx.par_path, params=params,
                        grp_aliases=ctx.info["grp_aliases"], create=create)

    # 2. Write the per-rundir record before anything is run or submitted, so a
    #    submitted job always has its record.
    _stage.write_record(rundir, params, ctx.command, ctx.executable, "staged", ctx.git_hash)

    # 3. Run / submit / stage-only, then record the status (and the job id).
    status, fields = "staged", {}
    if ctx.submit:
        _hpc.preparejob(ctx.template, rundir, ctx.executable, ctx.qos, ctx.mem,
                        ctx.wall, ctx.partition, ctx.account, ctx.omp, ctx.cpus,
                        ctx.jobname, ctx.email, ctx.mail_type, ctx.sbatch)
        status = "prepared"
        if ctx.run:
            out = _hpc.submitjob(rundir)
            status, fields = "submitted", {"job_id": out.split()[-1] if out else None}
    elif ctx.run:
        _hpc.runjob(rundir, ctx.executable, ctx.omp)
        status = "running"

    if status != "staged":
        _stage.update_record(rundir, status=status, **fields)

    return status
