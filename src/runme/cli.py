"""Command-line entrypoint for runme.

Dispatch:

* ``runme <subcommand> ...`` -> see :mod:`runme.commands` (config, info,
  queues, accounts, version, completions, sample, product, check, update) and
  ``runme case save`` (see :mod:`runme.cases`).
* ``runme ...`` (no subcommand) -> single simulation or ensemble run.

The run path takes ``-o RUNDIR`` and ``-p KEY=VAL`` overrides. A ``-p`` value
is "ensemble-shaped" when it contains a comma (list), a colon (range), or
``?`` (distribution); single-valued ``-p`` entries are fixed overrides applied
to every run, and any ensemble-shaped entry triggers ensemble mode.
"""
import os
import sys
import argparse
from collections import OrderedDict as odict

from runme import __version__
from runme import config as _config
from runme import commands as _commands
from runme import hpc as _hpc
from runme import stage as _stage
from runme import run as _run
from runme import sample as _sample


# ---------------------------------------------------------------------------
# Parameter spec parsing (shared by single-sim and ensemble)
# ---------------------------------------------------------------------------
def _is_ensemble_spec(spec):
    """True if the value spec denotes an ensemble dimension (list/range/dist)."""
    return (',' in spec) or ('?' in spec) or (':' in spec)


def _coerce(valstr):
    """Coerce a single value string to int, float, or str (matching the old -p)."""
    try:
        value = float(valstr)
        if value % 1 == 0 and '.' not in valstr:
            value = int(value)
        return value
    except ValueError:
        return valstr


def load_overlay(par_path, info):
    """Read the ``-n`` parameter file as an overlay dict.

    For projects that take the parameter file as an executable argument
    (``par_path_as_argument=true``) the ``-n`` file is staged and used directly,
    so there is nothing to overlay and ``{}`` is returned. Otherwise the file's
    parameters are returned as an ordered ``{group.name: value}`` dict so they
    can be merged into the project's default parameter files.
    """
    if par_path is None or info["par_path_as_argument"]:
        return odict()
    from runme.filetype import filetype_for_path
    with open(par_path) as f:
        return filetype_for_path(par_path).load(f)


def merge_overlay(overlay, fixed, grp_aliases):
    """Layer single-valued ``-p`` overrides on top of the ``-n`` overlay params.

    Overlay keys carry real group names (read from the namelist file) while
    ``-p`` keys may use group aliases, so the ``-p`` overrides are normalised
    first; that guarantees a ``-p`` override wins over the same overlay
    parameter instead of producing two divergent keys.
    """
    if not overlay:
        return fixed
    from runme.namelist import param_map_groups
    merged = odict(overlay)
    merged.update(param_map_groups(fixed, grp_aliases))
    return merged


def classify_params(raw):
    """Split raw ``key=spec`` entries into ensemble specs and fixed overrides.

    Returns ``(ensemble_specs, fixed)`` where ``ensemble_specs`` is the list of
    raw ``key=spec`` strings denoting ensemble dimensions and ``fixed`` is an
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


# ---------------------------------------------------------------------------
# Run parser (the default `runme ...` invocation)
# ---------------------------------------------------------------------------
def build_parser(hpc_config, info):
    """Build the run argument parser (single-sim and ensemble share it)."""
    exe_aliases_str = "; ".join(
        "{}={}".format(key, val) for key, val in info["exe_aliases"].items()
    )

    parser = argparse.ArgumentParser(
        prog="runme",
        description="Stage, run, and submit single simulations and ensembles.",
        epilog=("Subcommands: `runme config`, `runme info`, `runme queues`, "
                "`runme accounts`, `runme readme`, `runme check queues`, "
                "`runme case save`, `runme sample`, `runme product`, "
                "`runme update`, `runme version`, `runme completions`. "
                "Run `runme <subcommand> --help` for details."))

    parser.add_argument('-V', '--version', action='version',
                        version="%(prog)s " + __version__)
    parser.add_argument('-e', '--exe', type=str, default=info['exe_default'],
                        help="Executable file to use. Shortcuts: " + exe_aliases_str)
    parser.add_argument('-r', '--run', action="store_true",
                        help='Run the executable after preparing the job?')
    parser.add_argument('-s', '--submit', action="store_true",
                        help='Prepare a submit script (and submit it, with -r) '
                             'instead of running directly?')
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
    parser.add_argument('--debug', action="store_true",
                        help='Print a full traceback on error.')

    # Ensemble options.
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

    # `-n` is always registered so help is stable across projects. Whether it
    # is actually required (or ignored) depends on the project's
    # `par_path_as_argument` flag; that check happens in `build_context`.
    parser.add_argument('-n', dest='par_path', metavar='PAR_PATH', type=str, default=None,
                        help='Path to input parameter file/folder. Required when the '
                             'executable takes a par file as an argument (e.g. yelmo/yelmox); '
                             'ignored otherwise (e.g. climber).')

    return parser


def build_context(args, hpc_config, queues_all, info):
    """Resolve the member-independent run context shared by all runs.

    Expands the executable alias, builds the executable command line, resolves
    queue settings (when submitting), and validates input files. When the user
    is submitting, prints a one-block summary of the resolved cluster settings
    so any misconfiguration surfaces before sbatch sees it.
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

    if info["par_path_as_argument"] is True:
        if par_path is None:
            sys.exit("error: -n/PAR_PATH is required for this project "
                     "(par_path_as_argument=true in .runme/info.json).")
        exe_args = os.path.basename(par_path)
    else:
        # -n is optional here; when given it is an overlay whose parameters are
        # merged into the project's default parameter files (see _load_overlay),
        # not an executable argument.
        exe_args = ""

    profiler_prefix = ""
    if with_profiler:
        profiler_prefix = "amplxe-cl -c hotspots -r {} -- ".format("./")

    exe_rundir = "." if copy_exec else os.getcwd()
    executable = "{}{}/{} {}".format(profiler_prefix, exe_rundir, exe_fname, exe_args)

    # Resolve queue settings and print the submit summary first, so a missing
    # exe or par file doesn't hide what runme intended to do.
    qos = partition = wall = mem = None
    template = None
    if args.submit:
        hpc_queues = _config.select_hpc_queues(queues_all, hpc_config["hpc"])
        qos, partition, wall, mem = _hpc.resolve_queue(
            hpc_queues, hpc_config, args.queue, args.qos, args.part, args.wall, args.mem)
        template = _config.resolve_file(hpc_queues["job_template"])

        print("")
        print("Resolved submit settings:")
        print("  hpc       = {}".format(hpc_config["hpc"]))
        print("  account   = {}".format(args.account))
        print("  queue     = {}".format(args.queue if args.queue else "(individual overrides)"))
        print("  partition = {}".format(partition))
        print("  qos       = {}".format(qos))
        print("  wall      = {}".format(wall))
        print("  mem       = {}".format(mem if mem not in (None, -1) else "(unset)"))
        print("  omp       = {}".format(args.omp))
        print("  template  = {}".format(template))
        print("")

    if not os.path.isfile(exe_path):
        print("Input file does not exist: {}".format(exe_path))
        sys.exit()
    if par_path is not None and not os.path.isfile(par_path):
        print("Input file does not exist: {}".format(par_path))
        sys.exit()

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
        template=template,
        command=" ".join(sys.argv),
    )


# ---------------------------------------------------------------------------
# `runme update` -- self-upgrade from GitHub
# ---------------------------------------------------------------------------
RUNME_GIT_URL = "git+https://github.com/fesmc/runme.git"


def _update(rest):
    """Upgrade the installed runme package from GitHub via pip.

    Optional positional ``ref`` (``runme update <ref>``) selects a git branch,
    tag, or commit SHA — e.g. ``runme update dev`` installs from the ``dev``
    branch. With no ``ref``, pip pulls the repo's default branch.
    """
    import subprocess
    if rest and rest[0] in ("-h", "--help"):
        print("usage: runme update [<ref>]\n"
              "  <ref>  optional git branch, tag, or commit SHA "
              "(default: repo's default branch)")
        return 0
    url = RUNME_GIT_URL
    if rest:
        if len(rest) > 1:
            sys.stderr.write(
                "runme update: expected at most one ref, got {}\n".format(
                    " ".join(rest)))
            return 2
        url = "{}@{}".format(RUNME_GIT_URL, rest[0])
    cmd = [sys.executable, "-m", "pip", "install", "-U", url]
    print("Updating runme: {}".format(" ".join(cmd)))
    return subprocess.call(cmd)


# ---------------------------------------------------------------------------
# Entry point and dispatch
# ---------------------------------------------------------------------------
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


# Subcommands that need no project config and are dispatched before loading it.
# Each handler takes the remaining argv (after the subcommand name) and returns
# an exit code (0 = success).
_SUBCOMMANDS = {
    "sample":      lambda rest: _sample.main_sample(rest) or 0,
    "product":     lambda rest: _sample.main_product(rest) or 0,
    "update":      lambda rest: _update(rest),
    "version":     _commands.version,
    "config":      None,  # dispatched below (has nested subcommands)
    "info":        _commands.info,
    "queues":      _commands.queues,
    "accounts":    _commands.accounts,
    "readme":      _commands.readme,
    "completions": _commands.completions,
    "check":       None,  # dispatched below (has nested subcommands)
    "case":        None,  # dispatched below (has nested subcommands)
}

_CONFIG_SUBCOMMANDS = {
    "init":   _commands.config_init,
    "queues": _commands.config_queues,
    "info":   _commands.config_info,
    "submit": _commands.config_submit,
    "check":  _commands.config_check,
}


def _dispatch_config(rest):
    if not rest:
        sys.stderr.write(
            "usage: runme config <init|queues|info|submit|check>\n"
            "  init    scaffold .runme/ and seed config.toml from the tracked default\n"
            "  queues  install/refresh .runme/queues.json from the packaged template\n"
            "  info    install/refresh .runme/info.json from the packaged template\n"
            "  submit  show / install local submit_slurm{,_omp} templates\n"
            "  check   validate every config file without modifying anything\n"
        )
        return 1
    sub = rest[0]
    if sub not in _CONFIG_SUBCOMMANDS:
        sys.stderr.write("runme config: unknown subcommand '{}'\n".format(sub))
        return 1
    return _CONFIG_SUBCOMMANDS[sub](rest[1:])


def _dispatch_check(rest):
    # `runme check queues` is the SLURM-discovery command (separate from
    # `runme config check`, which is pure validation).
    if not rest or rest[0] != "queues":
        sys.stderr.write("usage: runme check queues [NAME]\n")
        return 1
    from runme import discover as _discover
    return _discover.main_check(rest) or 0


def _dispatch_case(rest):
    if not rest or rest[0] != "save":
        sys.stderr.write("usage: runme case save NAME -o RUNDIR\n"
                         "  save the parameters applied in RUNDIR as cases/NAME\n")
        return 1
    p = argparse.ArgumentParser(prog="runme case save")
    p.add_argument("name", help="case name (written to cases/NAME[.nml])")
    p.add_argument("-o", dest="rundir", metavar="RUNDIR", required=True,
                   help="run directory whose applied parameters are saved")
    ns = p.parse_args(rest[1:])

    grp_aliases = {}
    try:
        _, _, info = _config.load()
        grp_aliases = info.get("grp_aliases", {})
    except Exception:
        pass  # outside a project: save without group-alias normalisation

    from runme import cases as _cases
    _cases.save_case(ns.name, ns.rundir, grp_aliases)
    return 0


def _main(argv):
    # Top-level subcommand dispatch.
    if argv and argv[0] in _SUBCOMMANDS:
        sub, rest = argv[0], argv[1:]
        if sub == "config":
            return _dispatch_config(rest)
        if sub == "check":
            return _dispatch_check(rest)
        if sub == "case":
            return _dispatch_case(rest)
        return _SUBCOMMANDS[sub](rest)

    # --version still works outside a project (handy after `pip install`).
    if "-V" in argv or "--version" in argv:
        print("runme " + __version__)
        return 0

    # Load config. The full parser's help text and defaults come from it, so it
    # is required for a real run; tolerate its absence only so that --help can
    # still display generic options outside a project directory.
    want_help = "-h" in argv or "--help" in argv
    try:
        hpc_config, queues_all, info = _config.load()
    except Exception:
        if not want_help:
            raise
        hpc_config = {"omp": 1, "email": "", "account": "", "jobname": "",
                      "mail_type": []}
        queues_all = {}
        info = {"exe_default": None, "exe_aliases": {},
                "par_path_as_argument": False, "grp_aliases": {}}

    parser = build_parser(hpc_config, info)
    args = parser.parse_args(argv)

    # Resolve -n: a real path is used as-is; a bare name falls back to cases/.
    if args.par_path is not None:
        from runme import cases as _cases
        args.par_path = _cases.resolve_par_path(args.par_path)

    ensemble_specs, fixed = classify_params(args.p)
    ctx = build_context(args, hpc_config, queues_all, info)

    # Fold any -n overlay (for projects that don't take the par file as an
    # executable argument) into the fixed overrides applied to every run, with
    # -p winning on conflict.
    overlay = load_overlay(ctx.par_path, info)
    fixed = merge_overlay(overlay, fixed, info["grp_aliases"])

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
        _run.execute_one(args.rundir, fixed, ctx, create=True)
        if not ctx.dry_run:
            _stage.write_run_tables(args.rundir, list(fixed.keys()), list(fixed.values()), runid=0)

    return 0


if __name__ == "__main__":
    main()
