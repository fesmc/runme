"""Execute a single staged simulation.

Shared by the single-simulation path (:mod:`runme.cli`) and the ensemble path
(:mod:`runme.ensemble`), so one run directory is staged, run/submitted, and
recorded the same way regardless of how it was produced.

The member-independent context (resolved executable, queue settings, flags) is
carried in a plain ``argparse.Namespace`` built by :func:`runme.cli.build_context`.
"""
from runme import stage as _stage
from runme import hpc as _hpc


def execute_one(rundir, params, ctx, create=True):
    """Stage ``rundir`` with ``params`` and run/submit it per ``ctx``.

    Returns the run status: one of ``staged``, ``prepared``, ``running``,
    ``submitted``, or ``dry-run``.
    """
    if ctx.dry_run:
        print("[dry-run] {}".format(rundir))
        print("          command: {}".format(ctx.executable))
        print("          params : {}".format(dict(params or {})))
        return "dry-run"

    # 1. Populate the run directory.
    _stage.stage_rundir(rundir, ctx.info, ctx.exe_path, ctx.exe_alias,
                        par_path=ctx.par_path, params=params,
                        grp_aliases=ctx.info["grp_aliases"], create=create)

    # 2. Run / submit / stage-only.
    if ctx.submit:
        _hpc.preparejob(ctx.template, rundir, ctx.executable, ctx.qos, ctx.mem,
                        ctx.wall, ctx.partition, ctx.account, ctx.omp,
                        ctx.jobname, ctx.email, ctx.mail_type)
        if ctx.run:
            _hpc.submitjob(rundir)
            status = "submitted"
        else:
            status = "prepared"
    else:
        if ctx.run:
            _hpc.runjob(rundir, ctx.executable, ctx.omp)
            status = "running"
        else:
            status = "staged"

    # 3. Write the per-rundir record.
    _stage.write_record(rundir, params, ctx.command, ctx.executable, status)

    return status
