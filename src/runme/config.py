"""Configuration loading for runme.

File layout (project-relative, resolved from the current working directory):

* ``.runme/config.toml``          -- the user's active config (gitignored).
                                     Runme errors if this is missing.
* ``.runme/config.default.toml``  -- tracked template; only ever read by
                                     ``runme config init`` to seed config.toml.
* ``.runme/queues.json``          -- HPC queue aliases. Falls back through the
                                     user dir and the packaged template.
* ``.runme/info.json``            -- project model info (executables, par paths,
                                     links). Project-local; no fallback.

Generic resources (queues file, submit templates) resolve through a chain:
project -> ``~/.config/runme/`` -> the packaged ``templates/`` defaults. The
project-local files (``config.toml``, ``info.json``) do *not* use the chain.
"""
import os
import sys
import json

try:                           # Python 3.11+
    import tomllib as _toml
except ImportError:            # pragma: no cover - bootstrap fallback
    import tomli as _toml


# ---------------------------------------------------------------------------
# File layout
# ---------------------------------------------------------------------------
RUNME_DIR = ".runme"
CONFIG_PATH = os.path.join(RUNME_DIR, "config.toml")
CONFIG_DEFAULT_PATH = os.path.join(RUNME_DIR, "config.default.toml")
QUEUES_PATH = os.path.join(RUNME_DIR, "queues.json")
INFO_PATH = os.path.join(RUNME_DIR, "info.json")

USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "runme")
PACKAGE_TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")

# Files copied/scaffolded by ``runme config init``.
INIT_TEMPLATES = ("config.default.toml", "info.json", "queues.json")

# Validation key sets.
REQUIRED_CONFIG_KEYS = ["hpc", "account", "jobname", "omp", "mem",
                        "email", "mail_type"]
REQUIRED_INFO_KEYS = ["exe_default", "par_path_as_argument", "exe_aliases",
                      "grp_aliases", "par_paths", "files", "dir-special", "links"]


# ---------------------------------------------------------------------------
# Path resolution + JSON-with-doc loader
# ---------------------------------------------------------------------------
def resolve_file(path):
    """Resolve a generic config file through the project / user / package chain.

    Order: ``path`` -> ``~/.config/runme/<basename>`` -> packaged
    ``templates/<basename>``. Returns the first existing file, or ``path``
    unchanged so the caller can fail with a clear error on open.

    Used for files that are reasonably shared across projects (queues file,
    submit templates). Project-local files (``config.toml``, ``info.json``)
    bypass this chain.
    """
    if os.path.isfile(path):
        return path
    base = os.path.basename(path)
    for candidate in (os.path.join(USER_CONFIG_DIR, base),
                      os.path.join(PACKAGE_TEMPLATES, base)):
        if os.path.isfile(candidate):
            return candidate
    return path


def load_json_strip_doc(path):
    """Load a JSON file, dropping any top-level keys that start with ``_``.

    JSON has no comment syntax, so ``queues.json`` carries human-readable
    instructions under a top-level ``_doc`` key. Anything else starting with
    ``_`` is treated the same way and ignored at runtime.
    """
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load():
    """Load the runme configuration.

    Returns ``(hpc_config, queues_all, info)``. Raises a clear error if
    ``.runme/config.toml`` is missing -- the user must scaffold it via
    ``runme config init``.
    """
    if not os.path.isfile(CONFIG_PATH):
        raise Exception(
            "Config file '{}' not found.\n".format(CONFIG_PATH) +
            "This is probably the first time you are running runme here.\n" +
            "Run `runme config init` to scaffold .runme/ and create your "
            "config.toml from the tracked default."
        )

    with open(CONFIG_PATH, "rb") as f:
        hpc_config = _toml.load(f)

    queues_all = load_json_strip_doc(resolve_file(QUEUES_PATH))

    if not os.path.isfile(INFO_PATH):
        raise Exception(
            "Project info file '{}' not found.\n".format(INFO_PATH) +
            "Run `runme config info` to copy the template into place, then "
            "edit it for your model."
        )
    info = load_json_strip_doc(INFO_PATH)

    return hpc_config, queues_all, info


def select_hpc_queues(queues_all, hpc):
    """Select the queue block for ``hpc`` from the full queues mapping.

    Raises a clear error listing the available HPCs when ``hpc`` is absent.
    Only needed at submit time.
    """
    if hpc not in queues_all:
        raise Exception(
            "HPC '{}' not found in queues.json. Available HPCs: {}\n".format(
                hpc, ", ".join(queues_all.keys()) or "(none)") +
            "Set 'hpc' in {} to one of these, or add a block for it "
            "(see `runme queues --all` and `runme check queues`).".format(CONFIG_PATH))
    return queues_all[hpc]


# ---------------------------------------------------------------------------
# Small shared helpers (also used by command modules)
# ---------------------------------------------------------------------------
def confirm(prompt):
    """Yes/no prompt defaulting to yes on a bare Enter.

    Returns False on EOF (non-interactive stdin) so an existing file is not
    silently overwritten by automation.
    """
    try:
        resp = input(prompt).strip().lower()
    except EOFError:
        print()
        return False
    return resp in ("", "y", "yes")


def check_json_file(path, required_keys, label):
    """Validate that a JSON file exists, parses, and has the required keys.

    Prints a single ``[ok]``/``[x]``/``[!]`` line and returns True on success.
    Used by ``runme config check`` and ``runme info``.
    """
    if not os.path.isfile(path):
        print("  [x]  {} '{}' not found".format(label, path))
        return False
    try:
        data = load_json_strip_doc(path)
    except Exception as error:
        print("  [x]  {} '{}' is not valid JSON: {}".format(label, path, error))
        return False
    missing = [k for k in required_keys if k not in data]
    if missing:
        print("  [x]  {} '{}' missing keys: {}".format(label, path, ", ".join(missing)))
        return False
    print("  [ok] {} '{}'".format(label, path))
    return True


def check_toml_file(path, required_keys, label):
    """TOML counterpart to ``check_json_file`` for the active config."""
    if not os.path.isfile(path):
        print("  [x]  {} '{}' not found".format(label, path))
        return False
    try:
        with open(path, "rb") as f:
            data = _toml.load(f)
    except Exception as error:
        print("  [x]  {} '{}' is not valid TOML: {}".format(label, path, error))
        return False
    missing = [k for k in required_keys if k not in data]
    if missing:
        print("  [x]  {} '{}' missing keys: {}".format(label, path, ", ".join(missing)))
        return False
    print("  [ok] {} '{}'".format(label, path))
    return True
