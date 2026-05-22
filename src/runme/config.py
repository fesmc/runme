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

# Project configuration directory and the files `runme --init` scaffolds.
RUNME_DIR = ".runme"
INIT_TEMPLATES = ("info.json", "runme_config", "queues.json")

# Required keys for validation by `runme --init`.
REQUIRED_INFO_KEYS = ["exe_default", "par_path_as_argument", "exe_aliases",
                      "grp_aliases", "par_paths", "files", "dir-special", "links"]
REQUIRED_CONFIG_KEYS = ["hpc", "account", "jobname", "omp", "mem",
                        "queues_file", "info_file", "email", "mail_type"]


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
            "Required configuration file not found: {}\n".format(config_file) +
            "This is probably the first time you are running runme here.\n" +
            "Run `runme --config` to create it from the default and show its "
            "contents, then edit the settings and try again."
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
    peek.add_argument('--init', action='store_true')
    peek.add_argument('--list', nargs='?', const='__ALL__', default=None)
    peek.add_argument('--config', action='store_true')
    args, _ = peek.parse_known_args()

    if args.init:
        init_project()
        return True

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
    """Create (or refresh) and print the local runme config file.

    If the local config file is missing, it is copied from the default location.
    If it already exists, the user is asked whether to overwrite it from the
    default before printing. The default is resolved through the fallback chain
    (project .runme/runme_config -> ~/.config/runme -> packaged template), so
    this works even before the project has its own template.
    """
    resolved_default = resolve_file(default_config_file)

    if not os.path.isfile(config_file):
        print("Config file '{}' not found.".format(config_file))
        if os.path.isfile(resolved_default):
            shutil.copy(resolved_default, config_file)
            print("Copied default from '{}' to '{}'.".format(resolved_default, config_file))
        else:
            print("Default config '{}' also not found; nothing to show.".format(default_config_file))
            sys.exit(1)
    elif _confirm("Config file '{}' already exists. Overwrite from default? (Y/n) ".format(config_file)):
        if os.path.isfile(resolved_default):
            shutil.copy(resolved_default, config_file)
            print("Overwrote '{}' with default from '{}'.".format(config_file, resolved_default))
        else:
            print("Default config '{}' not found; keeping the existing file.".format(default_config_file))
    else:
        print("Keeping existing '{}'.".format(config_file))

    print()
    print("Current config ({}):".format(config_file))
    print("(edit this file directly to change settings)")
    print()
    with open(config_file) as f:
        contents = f.read()
    sys.stdout.write(contents)
    if not contents.endswith("\n"):
        sys.stdout.write("\n")

    return


# ---------------------------------------------------------------------------
# Project initialization / validation (`runme --init`)
# ---------------------------------------------------------------------------
def init_project(runme_dir=RUNME_DIR):
    """Create or validate the project's ``.runme/`` configuration directory.

    If ``.runme/`` does not exist, it is created and the minimal templates
    (info.json, runme_config, queues.json) are copied from the package; submit
    templates are left to the package fallback. If ``.runme/`` already exists,
    any genuinely-missing template files are added (never overwriting), the
    existing files are validated, and concrete fixes are suggested.
    """
    if not os.path.isdir(runme_dir):
        os.makedirs(runme_dir)
        for name in INIT_TEMPLATES:
            shutil.copy(os.path.join(PACKAGE_TEMPLATES, name), os.path.join(runme_dir, name))
        print("Created {}/ with templates: {}".format(runme_dir, ", ".join(INIT_TEMPLATES)))
        print("")
        print("Next steps:")
        print("  1. Edit {}/info.json for your model (executables, links, parameter files)."
              .format(runme_dir))
        print("  2. Set 'hpc' and 'account' in {}/runme_config (see `runme --list` for queues)."
              .format(runme_dir))
        print("     Add your cluster to {}/queues.json if it is not listed.".format(runme_dir))
        print("  3. Run `runme --config` to create your local {}, then run a simulation."
              .format(RUNME_CONFIG))
        return

    print("Found existing {}/ - checking configuration...\n".format(runme_dir))
    ok = True

    # Add any genuinely-missing template files (never overwrite an existing one).
    for name in INIT_TEMPLATES:
        dst = os.path.join(runme_dir, name)
        if not os.path.isfile(dst):
            shutil.copy(os.path.join(PACKAGE_TEMPLATES, name), dst)
            print("  [+]  created {} (was missing)".format(dst))

    # Validate info.json.
    ok &= _check_json(os.path.join(runme_dir, "info.json"), REQUIRED_INFO_KEYS, "info file")

    # Validate the config: prefer the active local .runme_config, else the template.
    if os.path.isfile(RUNME_CONFIG):
        config_path = RUNME_CONFIG
    else:
        config_path = os.path.join(runme_dir, "runme_config")
        print("  [!]  local {} not found - run `runme --config` to create it".format(RUNME_CONFIG))
    config_ok = _check_json(config_path, REQUIRED_CONFIG_KEYS, "config file")
    ok &= config_ok

    # Cross-checks that depend on a parseable config.
    if config_ok:
        conf = json.load(open(config_path))

        info_path = resolve_file(conf.get("info_file", ""))
        if not os.path.isfile(info_path):
            print("  [x]  info_file '{}' does not resolve to a file".format(conf.get("info_file")))
            ok = False

        queues_path = resolve_file(conf.get("queues_file", ""))
        if os.path.isfile(queues_path):
            try:
                queues = json.load(open(queues_path))
            except Exception as error:
                print("  [x]  queues file '{}' is not valid JSON: {}".format(queues_path, error))
                ok = False
                queues = {}
            hpc = conf.get("hpc")
            if hpc in ("CHANGEME", "", None):
                print("  [!]  'hpc' is still a placeholder - set it in {}".format(config_path))
                ok = False
            elif queues and hpc not in queues:
                print("  [x]  hpc '{}' not found in queues. Available: {}"
                      .format(hpc, ", ".join(queues.keys())))
                ok = False
        else:
            print("  [x]  queues_file '{}' does not resolve".format(conf.get("queues_file")))
            ok = False

        if conf.get("account") in ("CHANGEME", "", None):
            print("  [!]  'account' is still a placeholder - set it in {}".format(config_path))

    print("")
    print("All checks passed." if ok else "Some checks need attention (see above).")
    return


def _confirm(prompt):
    """Yes/no prompt defaulting to yes on a bare Enter.

    Returns False on EOF (e.g. non-interactive stdin) so an existing file is not
    overwritten unattended.
    """
    try:
        resp = input(prompt).strip().lower()
    except EOFError:
        print()
        return False
    return resp in ("", "y", "yes")


def _check_json(path, required_keys, label):
    """Validate that a JSON file exists, parses, and has the required keys."""
    if not os.path.isfile(path):
        print("  [x]  {} '{}' not found".format(label, path))
        return False
    try:
        data = json.load(open(path))
    except Exception as error:
        print("  [x]  {} '{}' is not valid JSON: {}".format(label, path, error))
        return False
    missing = [k for k in required_keys if k not in data]
    if missing:
        print("  [x]  {} '{}' missing keys: {}".format(label, path, ", ".join(missing)))
        return False
    print("  [ok] {} '{}'".format(label, path))
    return True
