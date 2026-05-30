"""Top-level subcommand implementations for runme.

Each function here implements one user-facing command:

* ``runme config init``     -- scaffold ``.runme/`` and copy templates
* ``runme config queues``   -- install / refresh / show the queues file
* ``runme config info``     -- install / refresh / show the project info file
* ``runme config check``    -- validate every config file without scaffolding
* ``runme info``            -- diagnostic: every file runme reads + validation
* ``runme queues``          -- concise queue table (current cluster or all)
* ``runme accounts``        -- show + run the sacctmgr query for accounts
* ``runme version``         -- print the version string
* ``runme completions``     -- emit a shell completion script

Dispatch lives in :mod:`runme.cli`.
"""
import os
import sys
import json
import shutil

from runme import __version__
from runme import config as _config


# ---------------------------------------------------------------------------
# `runme config init` -- scaffold .runme/
# ---------------------------------------------------------------------------
def config_init(argv):
    """Create or refresh ``.runme/``: scaffold templates and seed config.toml.

    Behaviour:

    * If ``.runme/`` does not exist, it is created and all tracked templates
      (``config.default.toml``, ``info.json``, ``queues.json``) are copied
      from the package.
    * If individual templates are missing they are copied in.
    * ``.runme/config.toml`` is created from ``config.default.toml`` if it is
      missing. An existing config.toml is *never* overwritten silently; rerun
      ``runme config init`` after deleting it if you want a fresh copy.

    Nothing tracked is overwritten. The command is idempotent.
    """
    if argv:
        _usage("runme config init")
        return 1

    if not os.path.isdir(_config.RUNME_DIR):
        os.makedirs(_config.RUNME_DIR)
        print("Created {}/".format(_config.RUNME_DIR))

    for name in _config.INIT_TEMPLATES:
        target = os.path.join(_config.RUNME_DIR, name)
        if not os.path.isfile(target):
            shutil.copy(os.path.join(_config.PACKAGE_TEMPLATES, name), target)
            print("  [+]  copied {} from packaged template".format(target))
        else:
            print("  [ok] {} (already present)".format(target))

    # Seed the active config from the tracked default.
    if not os.path.isfile(_config.CONFIG_PATH):
        if os.path.isfile(_config.CONFIG_DEFAULT_PATH):
            shutil.copy(_config.CONFIG_DEFAULT_PATH, _config.CONFIG_PATH)
            print("  [+]  created {} (copied from {})".format(
                _config.CONFIG_PATH, _config.CONFIG_DEFAULT_PATH))
        else:
            print("  [x]  cannot seed {}: {} is missing".format(
                _config.CONFIG_PATH, _config.CONFIG_DEFAULT_PATH))
            return 1
    else:
        print("  [ok] {} (already present; not overwritten)".format(_config.CONFIG_PATH))

    print("")
    print("Next steps:")
    print("  1. Edit {} (set 'hpc' and 'account' at minimum).".format(_config.CONFIG_PATH))
    print("     See `runme queues --all` for clusters and `runme accounts`")
    print("     for available accounts.")
    print("  2. Edit {} to describe your model's executables and inputs."
          .format(_config.INFO_PATH))
    print("  3. Run `runme info` to verify everything resolves.")
    return 0


# ---------------------------------------------------------------------------
# `runme config queues` / `runme config info` -- install + show a JSON file
# ---------------------------------------------------------------------------
def config_queues(argv):
    """Install / refresh / show ``.runme/queues.json``."""
    if argv:
        _usage("runme config queues")
        return 1
    return _install_and_show(
        target=_config.QUEUES_PATH,
        template_basename="queues.json",
        label="queues file",
    )


def config_info(argv):
    """Install / refresh / show ``.runme/info.json``."""
    if argv:
        _usage("runme config info")
        return 1
    return _install_and_show(
        target=_config.INFO_PATH,
        template_basename="info.json",
        label="info file",
    )


def _install_and_show(target, template_basename, label):
    """Shared workhorse: copy template to target (prompt if exists), then print.

    Header lines from the ``_doc`` array are printed as a banner above the
    file contents, so the instructions are visible without polluting the JSON.
    """
    packaged = os.path.join(_config.PACKAGE_TEMPLATES, template_basename)

    if not os.path.isfile(target):
        print("{} '{}' not found.".format(label.capitalize(), target))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy(packaged, target)
        print("Copied packaged template to '{}'.".format(target))
    elif _config.confirm(
            "{} '{}' already exists. Overwrite from packaged template? (Y/n) "
            .format(label.capitalize(), target)):
        shutil.copy(packaged, target)
        print("Overwrote '{}' with packaged template.".format(target))
    else:
        print("Keeping existing '{}'.".format(target))

    print("")
    print("Current {} ({}):".format(label, target))
    print("(edit this file directly to change settings)")
    print("")

    # Print the _doc banner first (if any), then the file as-is.
    with open(target) as f:
        raw = f.read()
    try:
        data = json.loads(raw)
    except Exception:
        data = None
    if isinstance(data, dict) and isinstance(data.get("_doc"), list):
        for line in data["_doc"]:
            print("# " + line if line else "#")
        print("")

    sys.stdout.write(raw)
    if not raw.endswith("\n"):
        sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# `runme config check` -- validate without scaffolding
# ---------------------------------------------------------------------------
def config_check(argv):
    """Validate every config file in place; do not create or modify anything.

    Useful in CI / pre-submit hooks. Returns non-zero on any failure.
    """
    if argv:
        _usage("runme config check")
        return 1

    print("Validating runme configuration ...\n")
    ok = True

    ok &= _config.check_toml_file(
        _config.CONFIG_PATH, _config.REQUIRED_CONFIG_KEYS, "config")

    queues_resolved = _config.resolve_file(_config.QUEUES_PATH)
    if os.path.isfile(queues_resolved):
        try:
            queues_all = _config.load_json_strip_doc(queues_resolved)
        except Exception as error:
            print("  [x]  queues '{}' is not valid JSON: {}".format(
                queues_resolved, error))
            ok = False
            queues_all = {}
        else:
            print("  [ok] queues '{}'".format(queues_resolved))
    else:
        print("  [x]  queues '{}' does not resolve".format(_config.QUEUES_PATH))
        ok = False
        queues_all = {}

    ok &= _config.check_json_file(
        _config.INFO_PATH, _config.REQUIRED_INFO_KEYS, "info")

    # Cross-checks: 'hpc' set and present in queues, 'account' set.
    if os.path.isfile(_config.CONFIG_PATH):
        try:
            with open(_config.CONFIG_PATH, "rb") as f:
                conf = _config._toml.load(f)
        except Exception:
            conf = {}
        hpc = conf.get("hpc")
        if hpc in ("CHANGEME", "", None):
            print("  [!]  'hpc' is still a placeholder in {}".format(_config.CONFIG_PATH))
            ok = False
        elif queues_all and hpc not in queues_all:
            print("  [x]  hpc '{}' not found in queues. Available: {}".format(
                hpc, ", ".join(queues_all.keys())))
            ok = False
        if conf.get("account") in ("CHANGEME", "", None):
            print("  [!]  'account' is still a placeholder in {}".format(_config.CONFIG_PATH))
            ok = False

    print("")
    print("All checks passed." if ok else "Some checks need attention (see above).")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# `runme info` -- diagnostic dump
# ---------------------------------------------------------------------------
def info(argv):
    """Show every file runme would read, where it resolved, and its status."""
    if argv:
        _usage("runme info")
        return 1

    print("runme {}".format(__version__))
    print("")
    print("Configuration files:")
    print("")

    _print_resolved(_config.CONFIG_PATH, "active config (TOML)",
                    "Per-host runme settings: hpc, account, jobname, omp, mem, "
                    "email, mail_type. Gitignored.")
    _print_resolved(_config.CONFIG_DEFAULT_PATH, "config template",
                    "Tracked template seeded by `runme config init`. Never "
                    "read at runtime.")
    _print_resolved(_config.QUEUES_PATH, "queues file (with fallback chain)",
                    "Per-cluster queue aliases. Resolves project -> "
                    "~/.config/runme/ -> packaged.")
    _print_resolved(_config.INFO_PATH, "project info",
                    "Model-specific: executables, par paths, links, files, "
                    "exe/group aliases. Project-local.")

    print("")
    print("Validation:")
    print("")
    ok = True
    ok &= _config.check_toml_file(
        _config.CONFIG_PATH, _config.REQUIRED_CONFIG_KEYS, "config")
    queues_resolved = _config.resolve_file(_config.QUEUES_PATH)
    ok &= _config.check_json_file(
        queues_resolved, [], "queues") if os.path.isfile(queues_resolved) else False
    ok &= _config.check_json_file(
        _config.INFO_PATH, _config.REQUIRED_INFO_KEYS, "info")

    # Summary of resolved settings.
    if os.path.isfile(_config.CONFIG_PATH):
        try:
            with open(_config.CONFIG_PATH, "rb") as f:
                conf = _config._toml.load(f)
            print("")
            print("Active settings:")
            print("  hpc      = {}".format(conf.get("hpc")))
            print("  account  = {}".format(conf.get("account")))
            print("  jobname  = {}".format(conf.get("jobname")))
            print("  omp      = {}".format(conf.get("omp")))
            print("  mem      = {}".format(conf.get("mem")))
            print("  email    = {}".format(conf.get("email") or "(none)"))
        except Exception as error:
            print("\n(could not read active settings: {})".format(error))

    return 0 if ok else 1


def _print_resolved(path, label, description):
    """Print one line per file: where it lives + a short description."""
    if os.path.isfile(path):
        location = path
        note = ""
    else:
        resolved = _config.resolve_file(path)
        if os.path.isfile(resolved):
            location = resolved
            if resolved.startswith(_config.PACKAGE_TEMPLATES):
                note = "  (packaged default)"
            elif resolved.startswith(_config.USER_CONFIG_DIR):
                note = "  (from ~/.config/runme/)"
            else:
                note = ""
        else:
            location = "(missing)"
            note = ""
    print("  {:<35s} {}{}".format(label + ":", location, note))
    print("    {}".format(description))


# ---------------------------------------------------------------------------
# `runme queues [--all] [--json]`
# ---------------------------------------------------------------------------
def queues(argv):
    """Print the queue alias table for the current cluster (or all)."""
    import argparse
    parser = argparse.ArgumentParser(prog="runme queues",
                                     description="Print the HPC queue alias table.")
    parser.add_argument("--all", action="store_true",
                        help="Show every cluster, not just the current one.")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of a table.")
    args = parser.parse_args(argv)

    queues_path = _config.resolve_file(_config.QUEUES_PATH)
    if not os.path.isfile(queues_path):
        print("Queues file not found: {}".format(_config.QUEUES_PATH))
        return 1
    queues_all = _config.load_json_strip_doc(queues_path)

    current_hpc = _current_hpc()

    if args.all:
        selected = queues_all
    else:
        if current_hpc is None:
            print("No active hpc found in {}. Use --all to list every cluster, "
                  "or run `runme config init` to scaffold a config."
                  .format(_config.CONFIG_PATH))
            return 1
        if current_hpc not in queues_all:
            print("Active hpc '{}' not found in {}. Use --all to list every "
                  "cluster.".format(current_hpc, queues_path))
            return 1
        selected = {current_hpc: queues_all[current_hpc]}

    if args.json:
        print(json.dumps(selected, indent=4))
        return 0

    _print_queue_table(selected, current_hpc)
    return 0


def _print_queue_table(queues_map, current_hpc):
    """Render a compact queue table, marking the active cluster with ``*``."""
    items = list(queues_map.items())
    for i, (hpc, block) in enumerate(items):
        marker = " *" if hpc == current_hpc else ""
        print("{}{}:".format(hpc, marker))
        qs = block.get("queues", {})
        if not qs:
            print("  (no queues defined)")
        else:
            alias_w = max(len(a) for a in qs.keys())
            qos_w = max(len(str(q.get("qos", ""))) for q in qs.values())
            part_w = max(len(str(q.get("partition", ""))) for q in qs.values())
            for alias, q in qs.items():
                print("  {a:<{aw}}  qos={qos:<{qw}}  partition={part:<{pw}}  wall={wall}".format(
                    a=alias, aw=alias_w,
                    qos=q.get("qos", ""), qw=qos_w,
                    part=q.get("partition", ""), pw=part_w,
                    wall=q.get("wall", "")))
        if i < len(items) - 1:
            print()


def _current_hpc():
    """Read the active 'hpc' from config.toml, or None if unavailable."""
    if not os.path.isfile(_config.CONFIG_PATH):
        return None
    try:
        with open(_config.CONFIG_PATH, "rb") as f:
            return _config._toml.load(f).get("hpc")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# `runme accounts` -- show the sacctmgr command + run it + parse the result
# ---------------------------------------------------------------------------
def accounts(argv):
    """Show the underlying sacctmgr command, run it, and print parsed accounts.

    The active account in ``.runme/config.toml`` (if any) is marked with ``*``.
    """
    if argv:
        _usage("runme accounts")
        return 1

    import getpass
    import subprocess as subp

    user = os.environ.get("USER") or getpass.getuser()
    cmd = ["sacctmgr", "-nP", "show", "assoc", "user=" + user, "format=Account"]
    print("Command: {}".format(" ".join(cmd)))
    print("")

    try:
        out = subp.check_output(cmd, stderr=subp.STDOUT)
    except FileNotFoundError:
        print("Error: 'sacctmgr' not found on PATH. `runme accounts` must be "
              "run on the cluster (login node).")
        return 1
    except subp.CalledProcessError as error:
        print("Error: sacctmgr failed: {}".format(
            error.output.decode("utf-8", "replace").strip()))
        return 1

    raw = out.decode("utf-8", "replace")
    seen = []
    for line in raw.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.append(name)

    if not seen:
        print("(no accounts found for user '{}')".format(user))
        return 1

    active = None
    if os.path.isfile(_config.CONFIG_PATH):
        try:
            with open(_config.CONFIG_PATH, "rb") as f:
                active = _config._toml.load(f).get("account")
        except Exception:
            active = None

    print("Accounts available to '{}':".format(user))
    for a in seen:
        marker = "  *" if a == active else "   "
        print("{} {}".format(marker, a))
    if active and active not in seen:
        print("")
        print("Note: 'account' in {} is '{}' but it is not in the list above."
              .format(_config.CONFIG_PATH, active))
    return 0


# ---------------------------------------------------------------------------
# `runme version`
# ---------------------------------------------------------------------------
def version(argv):
    """Print the runme version string."""
    if argv:
        _usage("runme version")
        return 1
    print("runme {}".format(__version__))
    return 0


# ---------------------------------------------------------------------------
# `runme completions {bash,zsh,fish}` -- emit a completion script
# ---------------------------------------------------------------------------
SUBCOMMANDS = [
    "sample", "product", "check", "update",
    "config", "info", "queues", "accounts", "version",
    "completions",
]
CONFIG_SUBCOMMANDS = ["init", "queues", "info", "check"]


def completions(argv):
    """Emit a shell completion script. Usage: ``runme completions <bash|zsh|fish>``.

    Source the output to enable tab completion of subcommand names. Run-mode
    flags (``-o``, ``-p``, ...) are not completed -- they're position- and
    project-dependent, and argparse already prints them on ``runme --help``.
    """
    if len(argv) != 1 or argv[0] not in ("bash", "zsh", "fish"):
        _usage("runme completions <bash|zsh|fish>")
        return 1
    shell = argv[0]
    subs = " ".join(SUBCOMMANDS)
    conf_subs = " ".join(CONFIG_SUBCOMMANDS)

    if shell == "bash":
        print(_BASH_COMPLETIONS.format(subs=subs, conf_subs=conf_subs))
    elif shell == "zsh":
        print(_ZSH_COMPLETIONS.format(subs=subs, conf_subs=conf_subs))
    elif shell == "fish":
        for s in SUBCOMMANDS:
            print("complete -c runme -n '__fish_use_subcommand' -a '{}'".format(s))
        for s in CONFIG_SUBCOMMANDS:
            print("complete -c runme -n '__fish_seen_subcommand_from config' "
                  "-a '{}'".format(s))
        print("complete -c runme -n '__fish_seen_subcommand_from check' -a 'queues'")
        print("complete -c runme -n '__fish_seen_subcommand_from completions' "
              "-a 'bash zsh fish'")
    return 0


_BASH_COMPLETIONS = """\
# runme bash completion. Source this file (or `eval "$(runme completions bash)"`).
_runme_complete() {{
    local cur prev sub
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    sub="${{COMP_WORDS[1]}}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{subs}" -- "$cur") )
        return 0
    fi
    case "$sub" in
        config)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "{conf_subs}" -- "$cur") )
            fi
            ;;
        check)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "queues" -- "$cur") )
            fi
            ;;
        completions)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") )
            fi
            ;;
    esac
    return 0
}}
complete -F _runme_complete runme
"""

_ZSH_COMPLETIONS = """\
# runme zsh completion. Source this file (or `eval "$(runme completions zsh)"`).
_runme() {{
    local -a subs conf_subs
    subs=({subs})
    conf_subs=({conf_subs})
    if (( CURRENT == 2 )); then
        _describe 'runme subcommand' subs
        return
    fi
    case "$words[2]" in
        config)
            (( CURRENT == 3 )) && _describe 'config subcommand' conf_subs
            ;;
        check)
            (( CURRENT == 3 )) && compadd queues
            ;;
        completions)
            (( CURRENT == 3 )) && compadd bash zsh fish
            ;;
    esac
}}
compdef _runme runme
"""


# ---------------------------------------------------------------------------
# Tiny helper for usage errors that point back at the right subcommand
# ---------------------------------------------------------------------------
def _usage(line):
    sys.stderr.write("usage: {}\n".format(line))
