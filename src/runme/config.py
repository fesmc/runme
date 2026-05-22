"""Configuration loading for runme.

Loads the project configuration files (resolved relative to the current working
directory, i.e. the model project directory you invoke ``runme`` from):

* ``.runme_config``            -- local, per-host settings (hpc, account, omp, email, ...)
* queues file                  -- HPC queue aliases (from ``hpc_config["queues_file"]``)
* info file                    -- executables, parameter files, links, copies
                                  (from ``hpc_config["info_file"]``)

Also handles the informational ``--list`` / ``--config`` options, which
short-circuit normal execution.

Phase 5 will extend file resolution with a project -> ``~/.config/runme`` ->
packaged-defaults fallback chain. For now the paths match the historical
script behaviour.
"""
import os
import sys
import json
import shutil
import argparse

# Local per-host config file, looked up in the current working directory.
RUNME_CONFIG = ".runme_config"
# Defaults shipped in the project's .runme/ directory.
DEFAULT_CONFIG = ".runme/runme_config"
DEFAULT_QUEUES = ".runme/queues.json"

# Fallback locations for generic files (queues, submit templates): a user-wide
# config directory and the defaults shipped inside the package.
USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "runme")
PACKAGE_TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


def resolve_file(path):
    """Resolve a configuration file through the fallback chain.

    Order: the given (project-relative) ``path`` -> ``~/.config/runme/<name>``
    -> the packaged ``templates/<name>`` default. Returns the first that exists,
    or ``path`` unchanged so the caller fails with a clear error on open.

    This lets a project ship only the files it customises (typically just
    ``info.json``) and inherit generic queues/submit templates from the package.
    """
    if os.path.isfile(path):
        return path
    base = os.path.basename(path)
    for candidate in (os.path.join(USER_CONFIG_DIR, base),
                      os.path.join(PACKAGE_TEMPLATES, base)):
        if os.path.isfile(candidate):
            return candidate
    return path


def load(config_file=RUNME_CONFIG):
    """Load the runme configuration.

    Returns ``(hpc_config, hpc_queues, info)`` where ``hpc_config`` is the local
    config dict, ``hpc_queues`` is the queue block for the configured HPC, and
    ``info`` is the model info dict (executables, parameter files, links, ...).
    """
    if not os.path.isfile(config_file):
        error_msg = (
            "Required json file containing hpc job defaults not found: {} \n".format(config_file) +
            "This is probably the first time you are running this script. \n" +
            "Copy the default file from the .runme config directory using the following command, \n" +
            "check the settings and then try again: \n\n cp {} {} \n".format(DEFAULT_CONFIG, config_file)
        )
        raise Exception(error_msg)

    hpc_config = json.load(open(config_file))

    # Load all queue information and extract the relevant one for the current hpc.
    # The queues file may come from the project, ~/.config/runme, or the package.
    queues_all = json.load(open(resolve_file(hpc_config["queues_file"])))
    hpc_queues = queues_all[hpc_config["hpc"]]

    # Load configuration info for the current setup (paths, links, aliases, etc).
    # info is project-specific, so this normally resolves to the project file.
    info = json.load(open(resolve_file(hpc_config["info_file"])))

    return hpc_config, hpc_queues, info


def handle_info_options(config_file=RUNME_CONFIG,
                        default_config_file=DEFAULT_CONFIG,
                        default_queues_file=DEFAULT_QUEUES):
    """Handle the informational ``--list`` and ``--config`` options.

    These short-circuit normal execution: they do not require ``-o RUNDIR`` and
    (for ``--list``) do not require an existing ``.runme_config``. Returns True
    if an option was handled and the caller should exit.
    """
    # Peek at argv without enforcing the full parser (which requires -o).
    peek = argparse.ArgumentParser(add_help=False)
    peek.add_argument('--list', nargs='?', const='__ALL__', default=None)
    peek.add_argument('--config', action='store_true')
    args, _ = peek.parse_known_args()

    if args.config:
        show_config(config_file, default_config_file)
        return True

    if args.list is not None:
        # Resolve queues file: prefer the path from .runme_config if present,
        # otherwise the default; in all cases fall through the resolution chain
        # (project -> ~/.config/runme -> packaged default).
        queues_path = default_queues_file
        if os.path.isfile(config_file):
            try:
                queues_path = json.load(open(config_file)).get("queues_file", default_queues_file)
            except Exception:
                pass

        queues_path = resolve_file(queues_path)
        if not os.path.isfile(queues_path):
            print("Queues file not found: {}".format(queues_path))
            sys.exit(1)

        queues_all = json.load(open(queues_path))
        list_queues(queues_all, args.list)
        return True

    return False


def list_queues(queues_all, hpc):
    """Print a compact table of queue aliases for one HPC, or for all HPCs."""
    if hpc == '__ALL__':
        hpcs = list(queues_all.keys())
    elif hpc in queues_all:
        hpcs = [hpc]
    else:
        print("Unknown HPC: '{}'. Available HPCs:".format(hpc))
        for k in queues_all.keys():
            print("  - {}".format(k))
        sys.exit(1)

    for i, h in enumerate(hpcs):
        queues = queues_all[h].get("queues", {})
        print("{}:".format(h))
        if not queues:
            print("  (no queues defined)")
        else:
            alias_w = max(len(a) for a in queues.keys())
            qos_w = max(len(str(q.get("qos", ""))) for q in queues.values())
            part_w = max(len(str(q.get("partition", ""))) for q in queues.values())
            for alias, q in queues.items():
                print("  {a:<{aw}}  qos={qos:<{qw}}  partition={part:<{pw}}  wall={wall}".format(
                    a=alias, aw=alias_w,
                    qos=q.get("qos", ""), qw=qos_w,
                    part=q.get("partition", ""), pw=part_w,
                    wall=q.get("wall", "")))
        if i < len(hpcs) - 1:
            print()

    return


def show_config(config_file, default_config_file):
    """Print contents of the local runme config file.

    If the local config file is missing, copy it from the default location (if
    available) and then print it. Hints that edits should be made directly.
    """
    if not os.path.isfile(config_file):
        print("Config file '{}' not found.".format(config_file))
        if os.path.isfile(default_config_file):
            shutil.copy(default_config_file, config_file)
            print("Copied default from '{}' to '{}'.".format(default_config_file, config_file))
        else:
            print("Default config '{}' also not found; nothing to show.".format(default_config_file))
            sys.exit(1)

    print("Current config ({}):".format(config_file))
    print("(edit this file directly to change settings)")
    print()
    with open(config_file) as f:
        contents = f.read()
    sys.stdout.write(contents)
    if not contents.endswith("\n"):
        sys.stdout.write("\n")

    return
