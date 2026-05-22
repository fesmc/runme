"""Command-line entrypoint for runme.

Phase 2 wires up the single-simulation flow: load config, build the parser,
stage the run directory, then run/submit (or stage only). Ensemble dispatch and
the ``sample`` / ``product`` subcommands are added in Phase 4.
"""
import os
import sys
import argparse

from runme import __version__
from runme import config as _config
from runme import hpc as _hpc
from runme import stage as _stage


class DictAction(argparse.Action):
    """Parse a list of ``key=val`` parameters into a dict.

    Converts values to an appropriate type (int, float, else str). For
    single-simulation runs only one value per parameter is allowed; comma lists
    (ensemble sweeps) are handled by the ensemble path added in Phase 4.

    Adapted from
    https://sumit-ghosh.com/articles/parsing-dictionary-key-value-pairs-kwargs-argparse-python/
    """

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, dict())
        for value in values:
            key, valstr = value.split('=')
            if ',' in valstr:
                raise Exception('Only one value allowed for each parameter using -p: {}={}'.format(key, valstr))
            try:
                value = float(valstr)
                if value % 1 == 0 and '.' not in valstr:
                    value = int(value)
            except ValueError:
                value = valstr
            getattr(namespace, self.dest)[key] = value


def build_parser(hpc_config, info):
    """Build the single-simulation argument parser.

    Defaults for ``--omp`` / ``--email`` / ``--account`` come from the loaded
    config; the executable-alias help text and the conditional ``-n`` argument
    come from the model info.
    """
    exe_aliases_str = "; ".join(
        "{}={}".format(key, val) for key, val in info["exe_aliases"].items()
    )

    parser = argparse.ArgumentParser(
        prog="runme",
        description="Stage, run, and submit single simulations and ensembles.",
    )

    parser.add_argument('-V', '--version', action='version', version="%(prog)s " + __version__)
    parser.add_argument('-e', '--exe', type=str, default=info['exe_default'],
                        help="Define the executable file to use here. Shortcuts: " + exe_aliases_str)
    parser.add_argument('-r', '--run', action="store_true",
                        help='Run the executable after preparing the job?')
    parser.add_argument('-s', '--submit', action="store_true",
                        help='Run the executable after preparing the job by submitting to the queue?')
    parser.add_argument('-q', '--queue', type=str, default=None,
                        help='Alias of the queue the job should be submitted to.')
    parser.add_argument('-w', '--wall', type=str, default=None,
                        help='HPC wall time "hh:mm:ss" (overrides settings given by queue alias)')
    parser.add_argument('--part', type=str, metavar="PARTITION", default=None,
                        help='HPC partition specification (overrides settings given by queue alias)')
    parser.add_argument('--qos', type=str, metavar="QOS", default=None,
                        help='HPC quality of service specification (overrides settings given by queue alias)')
    parser.add_argument('-m', '--mem', type=str, metavar="MEM", default=None,
                        help='HPC max memory per node specification (overrides settings given by queue alias)')
    parser.add_argument('--omp', type=int, metavar="OMP", default=hpc_config["omp"],
                        help='Number of threads for OpenMP (default = 1 implies no parallel computation)')
    parser.add_argument('--email', type=str, default=hpc_config["email"],
                        help='Email address for job notifications (overrides config settings).')
    parser.add_argument('--account', type=str, default=hpc_config["account"],
                        help='HPC account associated with job (overrides config settings).')
    parser.add_argument('-v', action="store_true", help='Verbose script output?')
    parser.add_argument('--list', nargs='?', const='__ALL__', default=None, metavar='HPC',
                        help='List queue aliases for the given HPC, or for all HPCs if no name is provided, then exit.')
    parser.add_argument('--config', action="store_true",
                        help='Show the current {} (copying the default from {} if missing), then exit.'.format(
                            _config.RUNME_CONFIG, _config.DEFAULT_CONFIG))

    parser.add_argument("-p", metavar="KEY=VALUE", nargs='+', action=DictAction,
                        help="Set a number of key-value pairs (no spaces around the = sign). "
                             'If a value contains spaces, quote it: foo="this is a sentence".')

    requiredNamed = parser.add_argument_group('required named arguments')
    requiredNamed.add_argument('-o', dest='rundir', metavar='RUNDIR', type=str, required=True,
                               help='Path where simulation will run and store output.')

    if info["par_path_as_argument"] is True:
        requiredNamed.add_argument('-n', dest='par_path', metavar='PAR_PATH', type=str, required=True,
                                   help='Path to input parameter file/folder.')

    return parser


def main(argv=None):
    # Informational options (--list / --config) short-circuit before requiring
    # config files or -o.
    if _config.handle_info_options():
        return

    # Load configuration (raises a helpful message if .runme_config is missing).
    hpc_config, hpc_queues, info = _config.load()

    parser = build_parser(hpc_config, info)
    args = parser.parse_args(argv)

    # Options
    exe_path = args.exe
    run = args.run
    submit = args.submit
    omp = args.omp
    par = args.p
    rundir = args.rundir
    par_path = getattr(args, 'par_path', None)

    # Config-derived job settings
    mail_type = hpc_config["mail_type"]
    jobname = hpc_config["jobname"]
    path_jobscript_template = hpc_queues["job_template"]

    copy_exec = True       # run the executable from inside the run directory
    with_profiler = False  # vtune profiler prefix (disabled)

    # Resolve queue settings only when submitting.
    qos = partition = wall = mem = None
    if submit:
        qos, partition, wall, mem = _hpc.resolve_queue(
            hpc_queues, hpc_config, args.queue, args.qos, args.part, args.wall, args.mem)

    # Expand executable alias if defined; recover the alias for par-path filtering.
    if exe_path in info["exe_aliases"]:
        exe_path = info["exe_aliases"].get(exe_path)
    exe_alias = next((k for k, v in info["exe_aliases"].items() if v == exe_path), None)
    print("exe_alias: {}".format(exe_alias))

    exe_fname = os.path.basename(exe_path)

    # Executable command-line argument (parameter file) when required.
    if info["par_path_as_argument"] is True:
        if copy_exec:
            exe_args = os.path.basename(par_path)
        else:
            exe_args = os.path.join(rundir, os.path.basename(par_path))
    else:
        exe_args = ""

    # Profiler prefix (disabled by default).
    if with_profiler:
        profiler_prefix = "amplxe-cl -c hotspots -r {} -- ".format("./" if copy_exec else rundir)
    else:
        profiler_prefix = ""

    # Make sure input file(s) exist.
    if not os.path.isfile(exe_path):
        print("Input file does not exist: {}".format(exe_path))
        sys.exit()
    if info["par_path_as_argument"] is True and not os.path.isfile(par_path):
        print("Input file does not exist: {}".format(par_path))
        sys.exit()

    # 1. Stage the run directory.
    _stage.stage_rundir(rundir, info, exe_path, exe_alias,
                        par_path=par_path, params=par,
                        grp_aliases=info["grp_aliases"], create=True)

    # 2. Build the executable command.
    exe_rundir = "." if copy_exec else os.getcwd()
    executable = "{}{}/{} {}".format(profiler_prefix, exe_rundir, exe_fname, exe_args)

    # 3. Run / submit / stage-only.
    if submit:
        _hpc.preparejob(path_jobscript_template, rundir, executable, qos, mem,
                        wall, partition, args.account, omp, jobname, args.email, mail_type)
        if run:
            _hpc.submitjob(rundir)
            status = "submitted"
        else:
            status = "prepared"
    else:
        if run:
            _hpc.runjob(rundir, executable, omp)
            status = "running"
        else:
            status = "staged"

    # 4. Write the per-rundir record.
    _stage.write_record(rundir, par, " ".join(sys.argv), executable, status)

    return


if __name__ == "__main__":
    main()
