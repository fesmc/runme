"""Discover HPC queue settings from SLURM and emit a ``queues.json`` block.

``runme check queues [NAME]`` introspects the cluster you are logged into and
prints a queue block ready to drop into ``queues.json``. A "queue" here is the
``(partition, qos, wall)`` triplet that SLURM actually accepts; the set of
usable triplets is taken from *your* associations (``sacctmgr show assoc``), so
the output is restricted to what you can submit rather than the full -- often
huge -- list of partitions and QOS on the system.

Walls are the tighter of the partition ``MaxTime`` and the qos ``MaxWall``.
Aliases are guessed from whichever axis varies (partition or qos); when both
vary the aliases fall back to ``queue1``, ``queue2``, ... for you to rename.
"""
import os
import sys
import json
import getpass
import subprocess as subp

from runme import config as _config


# ---------------------------------------------------------------------------
# Running SLURM commands
# ---------------------------------------------------------------------------
def _run(cmd):
    """Run a SLURM command and return its stdout, with clean errors."""
    try:
        out = subp.check_output(cmd, stderr=subp.STDOUT)
    except FileNotFoundError:
        raise Exception(
            "'{}' not found on PATH. `runme check queues` must be run on the "
            "cluster (login node), where the SLURM client tools are available."
            .format(cmd[0]))
    except subp.CalledProcessError as error:
        raise Exception("'{}' failed: {}".format(
            " ".join(cmd), error.output.decode("utf-8", "replace").strip()))
    return out.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# SLURM time parsing / formatting
# ---------------------------------------------------------------------------
_INFINITE = {"", "UNLIMITED", "INFINITE", "INVALID", "NONE", "NOT_SET", "N/A"}


def parse_slurm_time(text):
    """Parse a SLURM duration to seconds, or ``None`` for infinite/unset.

    Handles ``D-HH:MM:SS``, ``D-HH:MM``, ``D-HH``, ``HH:MM:SS``, ``MM:SS`` and
    bare-minute forms, matching the formats emitted by ``scontrol`` (partition
    ``MaxTime`` / ``DefaultTime``) and ``sacctmgr`` (qos ``MaxWall``).
    """
    if text is None:
        return None
    s = text.strip()
    if s.upper() in _INFINITE:
        return None

    days = 0
    if "-" in s:
        d, s = s.split("-", 1)
        days = int(d)
        # After a day field the remainder is HH[:MM[:SS]].
        parts = [int(p) for p in s.split(":")] if s else [0]
        h = parts[0] if len(parts) >= 1 else 0
        m = parts[1] if len(parts) >= 2 else 0
        sec = parts[2] if len(parts) >= 3 else 0
    else:
        parts = [int(p) for p in s.split(":")]
        if len(parts) == 3:
            h, m, sec = parts
        elif len(parts) == 2:
            # SLURM convention without a day field is MM:SS.
            h, m, sec = 0, parts[0], parts[1]
        else:
            h, m, sec = 0, parts[0], 0

    return days * 86400 + h * 3600 + m * 60 + sec


def format_hms(seconds):
    """Format seconds as ``H:MM:SS`` (hours may exceed 24, e.g. ``720:00:00``)."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return "{:02d}:{:02d}:{:02d}".format(h, m, s)


# ---------------------------------------------------------------------------
# Parsing SLURM inventory
# ---------------------------------------------------------------------------
def get_cluster_name():
    """Cluster name from ``scontrol show config`` (``ClusterName``), or None."""
    out = _run(["scontrol", "show", "config"])
    for line in out.splitlines():
        if line.strip().startswith("ClusterName"):
            _, _, value = line.partition("=")
            value = value.strip()
            if value and value.upper() not in _INFINITE:
                return value
    return None


def get_partitions():
    """Map partition name -> ``{"maxtime": str, "defaulttime": str}``.

    Parsed from ``scontrol show partition`` (insertion order preserved).
    """
    out = _run(["scontrol", "show", "partition"])
    partitions = {}
    name = None
    for token_line in out.split("PartitionName="):
        token_line = token_line.strip()
        if not token_line:
            continue
        name = token_line.split()[0]
        fields = {}
        for tok in token_line.split():
            if "=" in tok:
                k, _, v = tok.partition("=")
                fields[k] = v
        partitions[name] = {
            "maxtime": fields.get("MaxTime", ""),
            "defaulttime": fields.get("DefaultTime", ""),
        }
    return partitions


def get_qos():
    """Map qos name -> ``MaxWall`` string (blank when unset)."""
    out = _run(["sacctmgr", "-nP", "show", "qos", "format=Name,MaxWall"])
    qos = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        cols = line.split("|")
        name = cols[0].strip()
        maxwall = cols[1].strip() if len(cols) > 1 else ""
        if name:
            qos[name] = maxwall
    return qos


def get_associations(user):
    """Return ``(rows, accounts)`` from ``sacctmgr show assoc`` for ``user``.

    Each row is ``{"account", "partitions": [...], "qos": [...]}``; an empty
    list means "unrestricted" (all partitions / all qos), to be expanded by the
    caller. ``accounts`` is the ordered set of distinct accounts seen.
    """
    out = _run(["sacctmgr", "-nP", "show", "assoc", "user=" + user,
                "format=Account,Partition,QOS,DefaultQOS"])
    rows = []
    accounts = []
    for line in out.splitlines():
        if not line.strip():
            continue
        cols = (line.split("|") + ["", "", "", ""])[:4]
        account = cols[0].strip()
        partitions = [p for p in cols[1].split(",") if p.strip()]
        qos = [q for q in cols[2].split(",") if q.strip()]
        rows.append({"account": account, "partitions": partitions, "qos": qos})
        if account and account not in accounts:
            accounts.append(account)
    return rows, accounts


# ---------------------------------------------------------------------------
# Building triplets and aliases
# ---------------------------------------------------------------------------
def resolve_wall(partition, qos, partitions, qos_map):
    """Wall for a (partition, qos) pair: min of partition/qos limits.

    Falls back to the partition ``DefaultTime`` when both limits are infinite,
    then to ``24:00:00`` as a last resort placeholder.
    """
    pmax = parse_slurm_time(partitions.get(partition, {}).get("maxtime"))
    qmax = parse_slurm_time(qos_map.get(qos, ""))
    finite = [t for t in (pmax, qmax) if t is not None]
    if finite:
        return format_hms(min(finite))
    deftime = parse_slurm_time(partitions.get(partition, {}).get("defaulttime"))
    if deftime is not None:
        return format_hms(deftime)
    return "24:00:00"


def build_triplets(assoc_rows, partitions, qos_map):
    """Expand associations into a deduped, ordered list of usable triplets."""
    all_partitions = list(partitions.keys())
    all_qos = list(qos_map.keys())

    triplets = []
    seen = set()
    for row in assoc_rows:
        parts = row["partitions"] or all_partitions
        qoss = row["qos"] or all_qos
        for p in parts:
            for q in qoss:
                if (p, q) in seen:
                    continue
                seen.add((p, q))
                triplets.append({
                    "partition": p,
                    "qos": q,
                    "wall": resolve_wall(p, q, partitions, qos_map),
                })
    return triplets


def derive_aliases(triplets):
    """Name each triplet, guessing from the single varying axis when possible.

    Returns ``(aliases, ambiguous)``. If qos is constant and partitions are
    unique, alias by partition; if partition is constant and qos are unique,
    alias by qos; otherwise use ``queue1, queue2, ...`` and set ``ambiguous``.
    """
    parts = [t["partition"] for t in triplets]
    qoss = [t["qos"] for t in triplets]

    qos_constant = len(set(qoss)) == 1
    part_constant = len(set(parts)) == 1
    parts_unique = len(set(parts)) == len(parts)
    qos_unique = len(set(qoss)) == len(qoss)

    if qos_constant and parts_unique and len(parts) > 1:
        return list(parts), False
    if part_constant and qos_unique and len(qoss) > 1:
        return list(qoss), False
    if len(triplets) == 1:
        # A single triplet: name it after the partition (always defined).
        return [parts[0]], False

    return ["queue{}".format(i + 1) for i in range(len(triplets))], True


# ---------------------------------------------------------------------------
# Assembling and writing the block
# ---------------------------------------------------------------------------
def build_block(triplets, aliases, job_template=".runme/submit_slurm"):
    """Assemble the cluster block (job_template + ordered queues)."""
    queues = {}
    for alias, t in zip(aliases, triplets):
        queues[alias] = {"qos": t["qos"], "partition": t["partition"], "wall": t["wall"]}
    return {"job_template": job_template, "queues": queues}


def _target_queues_path():
    """Project path to write queues into (config's queues_file, else default)."""
    if os.path.isfile(_config.RUNME_CONFIG):
        try:
            conf = json.load(open(_config.RUNME_CONFIG))
            return conf.get("queues_file", _config.DEFAULT_QUEUES)
        except Exception:
            pass
    return _config.DEFAULT_QUEUES


def merge_block(name, block):
    """Merge ``block`` under key ``name`` into the project queues file.

    Existing clusters are preserved; an existing entry for ``name`` is only
    overwritten after confirmation. Returns the path written.
    """
    target = _target_queues_path()

    # Seed from any resolvable existing file so other clusters are kept.
    resolved = _config.resolve_file(target)
    base = {}
    if os.path.isfile(resolved):
        try:
            base = json.load(open(resolved))
        except Exception as error:
            raise Exception("existing queues file '{}' is not valid JSON: {}"
                            .format(resolved, error))

    if name in base and not _config._confirm(
            "Cluster '{}' already exists in {}. Overwrite it? (Y/n) ".format(name, target)):
        print("Keeping existing '{}' entry; nothing written.".format(name))
        return None

    base[name] = block

    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w") as f:
        json.dump(base, f, indent=4)
        f.write("\n")
    return target


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main_check(argv):
    """Handle ``runme check ...`` subcommands. Currently only ``queues``."""
    if not argv or argv[0] != "queues":
        print("usage: runme check queues [NAME]")
        sys.exit(1)

    name_override = argv[1] if len(argv) > 1 else None

    user = os.environ.get("USER") or getpass.getuser()
    print("Discovering SLURM queues usable by '{}' ...\n".format(user))

    partitions = get_partitions()
    qos_map = get_qos()
    assoc_rows, accounts = get_associations(user)

    if not assoc_rows:
        raise Exception("no associations found for user '{}' (sacctmgr show assoc). "
                        "Are you on the right cluster?".format(user))

    triplets = build_triplets(assoc_rows, partitions, qos_map)
    if not triplets:
        raise Exception("could not derive any usable (partition, qos) pairs "
                        "from your associations.")

    aliases, ambiguous = derive_aliases(triplets)

    # Cluster name: auto from SLURM, with interactive override.
    auto_name = name_override or get_cluster_name() or "my_cluster"
    if name_override:
        name = name_override
    else:
        try:
            entered = input("Enter cluster name ({}): ".format(auto_name)).strip()
        except EOFError:
            entered = ""
        name = entered or auto_name

    block = build_block(triplets, aliases)
    payload = {name: block}

    print()
    print(json.dumps(payload, indent=4))
    print()

    if ambiguous:
        print("Note: both partition and qos vary, so aliases default to "
              "queue1, queue2, ... - rename them in the queues file to "
              "something memorable once written.")
    else:
        print("Note: aliases were guessed from the varying field; rename them "
              "in the queues file if you prefer different names.")

    if accounts:
        print("Discovered account(s) for 'account' in {}: {}".format(
            _config.RUNME_CONFIG, ", ".join(accounts)))
    print()

    target = _target_queues_path()
    if _config._confirm("Merge this block into {}? (Y/n) ".format(target)):
        written = merge_block(name, block)
        if written:
            print("Wrote '{}' to {}.".format(name, written))
            print("Set \"hpc\": \"{}\" in {} (and check the aliases) to use it."
                  .format(name, _config.RUNME_CONFIG))
    else:
        print("Not written. Copy the block above into your queues file manually "
              "if you want it.")

    return
