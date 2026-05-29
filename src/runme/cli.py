"""Command-line entrypoint for runme.

Dispatch:

* ``runme sample ...`` / ``runme product ...`` -> generate an ensemble
  parameter file (see :mod:`runme.sample`).
* ``runme ... -i FILE`` or any ensemble-shaped ``-p`` spec -> ensemble mode
  (see :mod:`runme.ensemble`).
* otherwise -> single simulation.

A ``-p`` value is "ensemble-shaped" when it contains a comma (list), a colon
(range), or ``?`` (distribution). Single-valued ``-p`` entries are fixed
overrides applied to every run.
"""
import os
import sys
import argparse
from collections import OrderedDict as odict

from runme import __version__
from runme import config as _config
from runme import hpc as _hpc
from runme import stage as _stage
from runme import run as _run
from runme import sample as _sample


def _is_ensemble_spec(spec):
    """True if the value spec denotes an ensemble dimension (list/range/dist)."""
    return (',' in spec) or ('?' in spec) or (':' in spec)


def _coerce(valstr):
    """Coerce a single value string to int, float, or str (as the old -p did)."""
    try:
        value = float(valstr)
        if value % 1 == 0 and '.' not in valstr:
            value = int(value)
        return value
    except ValueError:
        return valstr


def classify_params(raw):
    """Split raw ``key=spec`` entries into ensemble specs and fixed overrides.

    Returns ``(ensemble_specs, fixed)`` where ``ensemble_specs`` is the list of
    raw ``key=spec`` strings that denote ensemble dimensions and ``fixed`` is an
    ordered dict of single-valued overrides.
    """
    ensemble_specs = []
    fixed = odict()
    for item in raw or []:
        key, spec = item.split('=', 1)
        if _is_ensemble_spec(spec):
            ensemble_specs.append(item)
        else:
            fixed[key] = _coerce(spec)
    return ensemble_specs, fixed


def build_parser(hpc_config, info):
    """Build the run argument parser (single-sim and ensemble share it)."""
    exe_aliases_str = "; ".join(
        "{}={}".format(key, val) for key, val in info["exe_aliases"].items()
    )

    parser = argparse.ArgumentParser(
        prog="runme",
        description="Stage, run, and submit single simulations and ensembles.",
        epilog="Subcommands: 'runme sample'/'runme product' generate ensemble parameter files; "
               "'runme check queues' discovers SLURM queues; 'runme update' upgrades runme itself.")

    parser.add_argument('-V', '--version', action='version', version="%(prog)s " + __version__)
    parser.add_argument('-e', '--exe', type=str, default=info['exe_default'],
                        help="Executable file to use. Shortcuts: " + exe_aliases_str)
    parser.add_argument('-r', '--run', action="store_true",
                        help='Run the executable after preparing the job?')
    parser.add_argument('-s', '--submit', action="store_true",
                        help='Prepare a submit script (and submit it, with -r) instead of running directly?')
    parser.add_argument('-q', '--queue', type=str, default=None,
                        help='Alias of the queue the job should be submitted to.')
    parser.add_argument('-w', '--wall', type=str, default=None,
                        help='HPC wall time "hh:mm:ss" (overrides queue alias)')
    parser.add_argument('--part', type=str, metavar="PARTITION", default=None,
                        help='HPC partition (overrides queue alias)')
    parser.add_argument('--qos', type=str, metavar="QOS", default=None,
                        help='HPC quality of service (overrides queue alias)')
    parser.add_argument('-m', '--mem', type=str, metavar="MEM", default=None,
                        help='HPC max memory per node (overrides queue alias)')
    parser.add_argument('--omp', type=int, metavar="OMP", default=hpc_config["omp"],
                        help='Number of OpenMP threads (default = 1 implies no parallel computation)')
    parser.add_argument('--email', type=str, default=hpc_config["email"],
                        help='Email for job notifications (overrides config).')
    parser.add_argument('--account', type=str, default=hpc_config["account"],
                        help='HPC account (overrides config).')
    parser.add_argument('-v', action="store_true", help='Verbose script output?')
    parser.add_argument('--debug', action="store_true", help='Print a full traceback on error.')
    parser.add_argument('--init', action="store_true",
                        help='Create or validate the .runme/ configuration directory, then exit.')
    parser.add_argument('--list', nargs='?', const='__ALL__', default=None, metavar='HPC',
                        help='List queue aliases for the given HPC (or all), then exit.')
    parser.add_argument('--config', action="store_true",
                        help='Show the current {} (copying the default from {} if missing), then exit.'.format(
                            _config.RUNME_CONFIG, _config.DEFAULT_CONFIG))

    # Ensemble options
    grp = parser.add_argument_group('ensemble options')
    grp.add_argument('-i', '--params-file', dest='params_file', default=None,
                     help='Run an ensemble from a parameter file (e.g. from `runme sample`).')
    grp.add_argument('-j', '--id', dest='runid', default=None,
                     metavar="I,J,...,START-STOP:STEP",
                     help='Select ensemble members to run (0-based; slurm --array syntax).')
    grp.add_argument('-a', '--auto-dir', dest='auto_dir', action='store_true',
                     help='Name run directories from parameter values instead of run id.')
    grp.add_argument('--include-default', dest='include_default', action='store_true',
                     help='Also run a "default" member with fixed parameters only.')
    grp.add_argument('--dry-run', dest='dry_run', action='store_true',
                     help='Show what would be done without creating or running anything.')

    parser.add_argument("-p", metavar="KEY=VALUE", nargs='+',
                        help="Set parameters. A single value is a fixed override applied to every run; "
                             "a comma list (a=1,2,3), range (a=0:10:5), or distribution (a=U?0,1) defines "
                             "an ensemble dimension.")

    requiredNamed = parser.add_argument_group('required named arguments')
    requiredNamed.add_argument('-o', dest='rundir', metavar='RUNDIR/OUTDIR', type=str, required=True,
                               help='Run directory (single sim) or experiment directory (ensemble).')

    if info["par_path_as_argument"] is True:
        requiredNamed.add_argument('-n', dest='par_path', metavar='PAR_PATH', type=str, required=True,
                                   help='Path to input parameter file/folder.')

    return parser


def build_context(args, hpc_config, hpc_queues, info):
    """Resolve the member-independent run context shared by all runs.

    Expands the executable alias, builds the executable command line, resolves
    queue settings (when submitting), and validates input files. Returns an
    ``argparse.Namespace``.
    """
    copy_exec = True       # run the executable from inside the run directory
    with_profiler = False  # vtune profiler prefix (disabled)

    exe_path = args.exe
    if exe_path in info["exe_aliases"]:
        exe_path = info["exe_aliases"].get(exe_path)
    exe_alias = next((k for k, v in info["exe_aliases"].items() if v == exe_path), None)
    print("exe_alias: {}".format(exe_alias))

    exe_fname = os.path.basename(exe_path)
    par_path = getattr(args, 'par_path', None)

    # Executable argument (parameter file) when required. With copy_exec the run
    # directory holds a copy, so the argument is the same for every member.
    if info["par_path_as_argument"] is True:
        exe_args = os.path.basename(par_path)
    else:
        exe_args = ""

    profiler_prefix = ""
    if with_profiler:
        profiler_prefix = "amplxe-cl -c hotspots -r {} -- ".format("./")

    exe_rundir = "." if copy_exec else os.getcwd()
    executable = "{}{}/{} {}".format(profiler_prefix, exe_rundir, exe_fname, exe_args)

    # Validate inputs.
    if not os.path.isfile(exe_path):
        print("Input file does not exist: {}".format(exe_path))
        sys.exit()
    if info["par_path_as_argument"] is True and not os.path.isfile(par_path):
        print("Input file does not exist: {}".format(par_path))
        sys.exit()

    # Queue settings (only needed when submitting).
    qos = partition = wall = mem = None
    if args.submit:
        qos, partition, wall, mem = _hpc.resolve_queue(
            hpc_queues, hpc_config, args.queue, args.qos, args.part, args.wall, args.mem)

    return argparse.Namespace(
        info=info,
        exe_path=exe_path,
        exe_alias=exe_alias,
        par_path=par_path,
        executable=executable,
        run=args.run,
        submit=args.submit,
        dry_run=args.dry_run,
        qos=qos, partition=partition, wall=wall, mem=mem,
        account=args.account, omp=args.omp,
        jobname=hpc_config["jobname"], email=args.email,
        mail_type=hpc_config["mail_type"],
        template=_config.resolve_file(hpc_queues["job_template"]),
        command=" ".join(sys.argv),
    )


RUNME_GIT_URL = "git+https://github.com/fesmc/runme.git"


def _update():
    """Upgrade the installed runme package from GitHub via pip."""
    import subprocess
    cmd = [sys.executable, "-m", "pip", "install", "-U", RUNME_GIT_URL]
    print("Updating runme: {}".format(" ".join(cmd)))
    return subprocess.call(cmd)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        return _main(argv)
    except SystemExit:
        raise
    except Exception as error:
        if "--debug" in argv:
            raise
        print("ERROR: " + str(error))
        print("ERROR: use --debug to print the full traceback")
        sys.exit(1)


def _main(argv):
    # Subcommands generate ensemble parameter files; they need no config or -o.
    if argv and argv[0] == "sample":
        return _sample.main_sample(argv[1:])
    if argv and argv[0] == "product":
        return _sample.main_product(argv[1:])

    # `runme check queues [NAME]` introspects the cluster's SLURM queues and
    # emits a queues.json block; it needs no project config or -o.
    if argv and argv[0] == "check":
        from runme import discover as _discover
        return _discover.main_check(argv[1:])

    # `runme update` upgrades the installed package from GitHub; it needs no
    # project config or -o.
    if argv and argv[0] == "update":
        return _update()

    # --version works from anywhere, without a project configuration.
    if "-V" in argv or "--version" in argv:
        print("runme " + __version__)
        return

    # Informational options (--list / --config) short-circuit before config/-o.
    if _config.handle_info_options():
        return

    # Load config. The full parser's help text and defaults come from it, so it
    # is required for a real run; tolerate its absence only so that --help can
    # still display the generic options outside a project directory.
    want_help = "-h" in argv or "--help" in argv
    try:
        hpc_config, hpc_queues, info = _config.load()
    except Exception:
        if not want_help:
            raise
        hpc_config = {"omp": 1, "email": "", "account": "", "jobname": "", "mail_type": []}
        hpc_queues = {"job_template": ""}
        info = {"exe_default": None, "exe_aliases": {},
                "par_path_as_argument": False, "grp_aliases": {}}

    parser = build_parser(hpc_config, info)
    args = parser.parse_args(argv)

    ensemble_specs, fixed = classify_params(args.p)
    ctx = build_context(args, hpc_config, hpc_queues, info)

    is_ensemble = bool(args.params_file) or bool(ensemble_specs)

    if is_ensemble:
        from runme import ensemble as _ensemble
        from runme.params import XParams, MultiParam, Param

        if args.params_file:
            if ensemble_specs:
                parser.error("in -i/--params-file mode, -p overrides must be single-valued "
                             "(no commas, ranges, or distributions)")
            xparams = XParams.read(args.params_file)
        else:
            for spec in ensemble_specs:
                if '?' in spec:
                    parser.error("continuous distributions require the `sample` subcommand: "
                                 "`runme sample ... -o FILE`, then `runme -i FILE ...`")
            xparams = MultiParam([Param.parse(spec) for spec in ensemble_specs]).product()

        indices = _ensemble.parse_slurm_array_indices(args.runid) if args.runid else None
        _ensemble.run(ctx, xparams, fixed, expdir=args.rundir, indices=indices,
                      autodir=args.auto_dir, include_default=args.include_default)
    else:
        # Single simulation.
        _run.execute_one(args.rundir, fixed, ctx, create=True)
        if not ctx.dry_run:
            _stage.write_run_tables(args.rundir, list(fixed.keys()), list(fixed.values()), runid=0)

    return


if __name__ == "__main__":
    main()
