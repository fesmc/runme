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
    print("Note: queues.json is provided by the packaged default; run")
    print("`runme config queues` if you need a local copy to customise.")
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
    """Show the active queues file; offer to install a local copy if missing.

    Order:

    1. Resolve and print whatever queues file runme is currently reading
       (project, ~/.config/runme/, or the packaged default), prefixed with
       the ``## Queues`` section of the packaged README.
    2. Only if ``.runme/queues.json`` does *not* exist locally, offer to
       copy the packaged template in so the user can customise it.

    The packaged default is good enough for most projects -- copying it in
    is opt-in to avoid useless duplication.
    """
    if argv:
        _usage("runme config queues")
        return 1

    resolved = _config.resolve_file(_config.QUEUES_PATH)
    if not os.path.isfile(resolved):
        print("Queues file not found anywhere (not in project, "
              "~/.config/runme/, or the packaged templates).")
        return 1

    print("Current queues file ({}):".format(resolved))
    print("")
    _print_readme_section("Queues")
    _print_file(resolved)

    if not os.path.isfile(_config.QUEUES_PATH):
        print("")
        print("Queues file '{}' not found.".format(_config.QUEUES_PATH))
        print("To add/modify queue information, a local version is needed.")
        if _config.confirm("Copy packaged template to '{}'? (Y/n) "
                           .format(_config.QUEUES_PATH)):
            parent = os.path.dirname(_config.QUEUES_PATH)
            if parent:
                os.makedirs(parent, exist_ok=True)
            packaged = os.path.join(_config.PACKAGE_TEMPLATES, "queues.json")
            shutil.copy(packaged, _config.QUEUES_PATH)
            print("Copied packaged template to '{}'.".format(_config.QUEUES_PATH))
        else:
            print("Not copied. Re-run `runme config queues` to install a local "
                  "copy later.")
    return 0


def config_info(argv):
    """Install / refresh / show ``.runme/info.json``."""
    if argv:
        _usage("runme config info")
        return 1
    return _install_and_show(
        target=_config.INFO_PATH,
        template_basename="info.json",
        label="info file",
        readme_section="Info",
    )


def _install_and_show(target, template_basename, label, readme_section):
    """Install (or refresh) a project-local file with no fallback, then print.

    Used for ``info.json``: there is no sensible fallback chain, so a missing
    file is copied in immediately; an existing file prompts for overwrite.
    The matching README section (from the packaged ``README.md``) is shown
    as a banner above the file contents.
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
    _print_readme_section(readme_section)
    _print_file(target)
    return 0


# ---------------------------------------------------------------------------
# README section banner + raw file printing
# ---------------------------------------------------------------------------
def _read_readme_section(name):
    """Return the lines under ``## <name>`` in the packaged ``README.md``.

    Case-insensitive heading match. Stops at the next ``## ``. Surrounding
    blank lines are stripped. Returns ``[]`` if the README or section is
    missing, so callers can degrade silently when docs are unavailable.
    """
    path = os.path.join(_config.PACKAGE_TEMPLATES, "README.md")
    if not os.path.isfile(path):
        return []
    target = name.strip().lower()
    body = []
    in_section = False
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.startswith("## "):
                if in_section:
                    break
                in_section = line[3:].strip().lower() == target
                continue
            if in_section:
                body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def _print_readme_section(name):
    """Print a README section as a ``#``-prefixed banner, plus a blank line."""
    lines = _read_readme_section(name)
    if not lines:
        return
    for line in lines:
        print("# " + line if line else "#")
    print("")


def _print_file(path):
    """Print a file's contents verbatim, ensuring a trailing newline."""
    with open(path) as f:
        raw = f.read()
    sys.stdout.write(raw)
    if not raw.endswith("\n"):
        sys.stdout.write("\n")


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
    _print_resolved(os.path.join(_config.RUNME_DIR, "submit_slurm"),
                    "submit template",
                    "SLURM job script template. Substitutes <QOS>, <PARTITION>, "
                    "<WALL>, <MEM>, <JOBNAME>, <ACCOUNT>, <CMD>, etc. "
                    "Resolves project -> ~/.config/runme/ -> packaged.")
    _print_resolved(os.path.join(_config.RUNME_DIR, "submit_slurm_omp"),
                    "submit template (OMP)",
                    "OMP fragment spliced in when omp > 0. Sets cpus-per-task "
                    "and OMP_* env vars. Same fallback chain.")

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
            _print_hpc_not_found(current_hpc, queues_path, queues_all)
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


def _print_hpc_not_found(current_hpc, queues_path, queues_all):
    """Print a hint-rich error when the active hpc isn't in the queues file.

    Branches:
    * placeholder ``CHANGEME`` -> first-time-setup hint pointing at config.toml.
    * unknown name -> list available clusters and walk the user through the
      two ways to proceed, so nobody tries to edit the packaged file.

    When the resolved path is the packaged template, the path annotation
    ``(default queues list - do not edit)`` is appended inline.
    """
    available = ", ".join(queues_all.keys()) or "(none)"
    annotation = ""
    if queues_path.startswith(_config.PACKAGE_TEMPLATES):
        annotation = " (default queues list - do not edit)"

    if current_hpc in ("CHANGEME", "", None):
        print("Active hpc is still the placeholder '{}'.".format(current_hpc))
        print("Edit 'hpc' in {} to one of the available clusters."
              .format(_config.CONFIG_PATH))
        print("")
        print("Available clusters: {}".format(available))
        print("Run `runme queues --all` to see the full table.")
        return

    print("Active hpc '{}' not found in {}{}.".format(
        current_hpc, queues_path, annotation))
    print("Available clusters: {}".format(available))
    print("To use an hpc for submitting jobs, either:")
    print("  * update 'hpc' in {} to match an available cluster listed above, or"
          .format(_config.CONFIG_PATH))

    if os.path.isfile(_config.QUEUES_PATH):
        # Local copy already exists -- they just need to edit it. Don't
        # suggest `config queues` (would imply installing on top of the file
        # they already have).
        print("  * add '{}' to {} by hand.".format(current_hpc, _config.QUEUES_PATH))
        print("      - Note, you can run `runme check queues` on the cluster login node to")
        print("        autodiscover its (partition, qos, wall) triplets.")
    else:
        print("  * add '{}' to a local version of the queues list in {}:"
              .format(current_hpc, _config.QUEUES_PATH))
        print("      - Run `runme config queues` to install a local copy of")
        print("        queues.json under .runme/ that you can edit by hand.")
        print("      - Run `runme check queues` on the cluster login node to")
        print("        autodiscover its (partition, qos, wall) triplets.")


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
# `runme readme` -- print the packaged README in full
# ---------------------------------------------------------------------------
def readme(argv):
    """Print the packaged README.md to stdout."""
    if argv:
        _usage("runme readme")
        return 1
    path = os.path.join(_config.PACKAGE_TEMPLATES, "README.md")
    if not os.path.isfile(path):
        print("README not found in packaged templates: {}".format(path))
        return 1
    _print_file(path)
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
    "config", "info", "queues", "accounts", "readme", "version",
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
