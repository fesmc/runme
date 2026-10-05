"""Fortran namelist read/write.

Vendored from ``runner.ext.namelist`` (originally adapted from
https://github.com/leifdenby/namelist_python). Python 3 only. The
:class:`~runme.filetype.FileType` base lives in :mod:`runme.filetype` alongside
the other formats and the extension dispatcher.

The public helpers used by runme are :func:`param_write_to_files` (write a dict
of ``group.name`` parameters into one or more parameter files, each in the
format implied by its extension) and the :class:`Namelist` format itself.
"""
from collections import OrderedDict as odict
import re
from itertools import groupby

from runme.filetype import FileType, filetype_for_path


class ParamNml(object):
    def __init__(self, group, name, value, help=None):
        self.group = group
        self.name = name
        self.value = value
        self.help = help


class Namelist(FileType):
    """Namelist format."""

    def __init__(self, sep='.'):
        self.sep = sep

    def dumps(self, params):
        pars = []
        for longname, value in params.items():
            group, name = longname.split(self.sep)
            pars.append(ParamNml(group, name, value))
        return format_nml(pars)

    def loads(self, string):
        params = parse_nml(string)
        return odict([(p.group + self.sep + p.name, p.value) for p in params])


def parse_nml(string, ignore_comments=False):
    """Parse a string namelist, and return a list of param bundles
    with four attrs: name, value, help, group.
    """
    group_re = re.compile(r'&([^&]+)/', re.DOTALL)  # allow blocks to span multiple lines
    # array_re = re.compile(r'(\w+)\((\d+)\)')
    # string_re = re.compile(r"[\'\"]*[\'\"]")

    # list of parameters
    params = []

    filtered_lines = []
    for line in string.split('\n'):
        line = line.strip()
        if line == "":
            continue
        # remove comments, since they may have forward-slashes
        # set ignore_comments to True if you want to keep them.
        if line.startswith('!'):
            continue
        if ignore_comments and '!' in line:
            line = line[:line.index('!')]

        filtered_lines.append(line)

    group_blocks = re.findall(group_re, "\n".join(filtered_lines))

    for i, group_block in enumerate(group_blocks):
        group_lines = group_block.split('\n')
        group_name = group_lines.pop(0).strip()
        # check for comments
        if "!" in group_name:
            i = group_name.index("!")
            group_name = group_name[:i].strip()

        # some lines are continuation of previous lines: filter
        joined_lines = []
        for line in group_lines:
            line = line.strip()
            if '=' in line:
                joined_lines.append(line)
            elif line == '':
                pass
            else:
                # continuation of previous line
                joined_lines[-1] += line
        group_lines = joined_lines

        for line in group_lines:
            name, value, comment = _parse_line(line)
            param = ParamNml(group_name, name, value, help=comment)
            params.append(param)

    return params


def _parse_line(line):
    "parse a line within a block"
    # commas at the end of lines seem to be optional
    comment = ""
    if '!' in line:
        sep = line.index("!")
        comment = line[sep + 1:].strip()
        line = line[:sep].strip()

    if line.endswith(','):
        line = line[:-1]

    k, v = line.split('=')
    name = k.strip()
    value = _parse_value(v.strip())
    return name, value, comment


def _parse_value(variable_value):
    """Try to parse a single value, raise an exception if no single value is matched."""
    try:
        parsed_value = int(variable_value)
    except ValueError:
        try:
            parsed_value = float(variable_value)
        except ValueError:
            if variable_value.lower() in ['.true.', 't', 'true']:
                parsed_value = True
            elif variable_value.lower() in ['.false.', 'f', 'false']:
                parsed_value = False
            elif variable_value.startswith("'") \
                    and variable_value.endswith("'") \
                    and variable_value.count("'") == 2 \
                    or variable_value.startswith('"') \
                    and variable_value.endswith('"') \
                    and variable_value.count('"') == 2:
                parsed_value = variable_value[1:-1]
            elif variable_value.startswith("/") and variable_value.endswith("/"):
                # array /3,4,5/
                parsed_value = _parse_array(variable_value[1:-1].split(','))
            elif "," in variable_value:
                # array 3, 4, 5
                parsed_value = _parse_array(variable_value.split(','))
            elif '*' in variable_value:
                # 3*4 means [4, 4, 4, 4] ==> handled in _parse_array
                parsed_value = _parse_array([variable_value])
            elif len(variable_value.split()) > 1:
                # array 3 4 5
                parsed_value = _parse_array(variable_value.split())
            else:
                print("Parsing ERROR: >>>{}<<<".format(variable_value))
                raise ValueError(variable_value)
    return parsed_value


def _parse_array(values):
    """Parse a list of (string) values representing a fortran array
    and return a python list.
    """
    assert type(values) is list
    parsed_value = []
    for v in values:
        if '*' in v:
            # 3* "a" === "a", "a", "a"
            mult, val = v.split('*')
            parsed_value.extend(int(mult) * [_parse_value(val.strip())])
        else:
            parsed_value.append(_parse_value(v))
    return parsed_value


def format_nml(params):
    """Format a flat parameter list to be written in the namelist."""
    lines = []
    for group_name, group_params in groupby(params, lambda x: x.group):
        if group_name == "":
            print(list(group_params))
            raise ValueError("Group not defined. Cannot write to namelist.")
        lines.append("&{}".format(group_name))
        for param in group_params:
            if isinstance(param.value, list):
                nmstr = "{:15}".format(param.name)
                line = " {} = {}".format(nmstr, " ".join([_format_value(v) for v in param.value]))
            else:
                nmstr = "{:15}".format(param.name)
                line = " {} = {}".format(nmstr, _format_value(param.value))
            line = "{:30}".format(line)
            if param.help:
                line += ' ! ' + param.help
            lines.append(line)
        lines.append("/")
    return "\n".join(lines) + "\n"


def _format_value(value):
    """Format a value into fortran's namelist format (return a string)."""
    if isinstance(value, bool):
        return value and '.true.' or '.false.'
    else:
        return "{}".format(repr(value))


def nml_update_if_exists(par, new):
    "Only update keys if they already exist."
    for key in new:
        if key in par:
            par.update({key: new.get(key)})
    return par


def param_write_to_files(params, nml_src_paths, nml_dst_paths, grp_aliases=None,
                         defaults_paths=None):
    """Write parameters from a dict to one or more destination parameter files,
    given the input parameter file(s), substituting group names by their aliases
    when necessary.

    With ``defaults_paths`` (the project's ``par_defaults``), a parameter absent
    from the parameter files but declared in the defaults is inserted into the
    file holding its group.
    """
    # First expand input parameter group-name aliases if available
    if grp_aliases is not None and len(grp_aliases) > 0:
        params_mapped = param_map_groups(params, grp_aliases)
    else:
        params_mapped = params

    # Load the input parameter files and the defaults declaring all parameters
    pars_src = [_load_params(path) for path in nml_src_paths]
    defaults_paths = list(defaults_paths or [])
    defaults = odict()
    for path in defaults_paths:
        defaults.update(_load_params(path))

    # Next, check to make sure desired parameters exist, convert each value to
    # the type of its current value, and place the new ones
    refs = param_check_all(params_mapped, pars_src, nml_src_paths, defaults, defaults_paths)
    params_mapped = odict((key, param_coerce(val, refs[key])) for key, val in params_mapped.items())
    new = odict((key, val) for key, val in params_mapped.items()
                if not any(key in d for d in pars_src))
    inserts = param_assign_new(new, pars_src, nml_src_paths)

    # If everything was ok, loop over files and write new parameter values
    for params_now, params_new, par_dst_path in zip(pars_src, inserts, nml_dst_paths):
        params_now = nml_update_if_exists(params_now, params_mapped)
        params_now = param_insert(params_now, params_new)
        with open(par_dst_path, 'w') as f:
            filetype_for_path(par_dst_path).dump(params_now, f)

    return


def _load_params(path):
    """Load a parameter file in the format implied by its extension."""
    with open(path) as f:
        return filetype_for_path(path).load(f)


def _group(key):
    return key.partition('.')[0]


def _name(key):
    return key.rpartition('.')[2]


def param_check_all(params, pars_src, par_paths, defaults=None, defaults_paths=()):
    """Check whether all parameters defined in a dict exist in one or more input
    parameter files or, failing that, in the defaults.

    Defaults are looked up under the canonical group name (see
    :func:`group_renames`); a canonical group that the parameter files rename is
    rejected so the value cannot land in a group the model never reads.

    Returns the current (reference) value of every parameter, from the
    parameter files or else the defaults.
    """
    defaults = defaults or {}

    # Collect the current values from all files
    all_values = odict()
    for d in pars_src:
        all_values.update(d)

    renames, renamed = group_renames(defaults, pars_src + [params])

    misnamed = []
    missing = []
    refs = odict()
    for key in params:
        group = _group(key)
        canonical = "{}.{}".format(renames.get(group, group), _name(key))
        if group in renamed:
            misnamed.append(key)
        elif key in all_values:
            refs[key] = all_values[key]
        elif canonical in defaults:
            refs[key] = defaults[canonical]
        else:
            missing.append(key)

    if len(misnamed) > 0:
        lines = []
        for key in misnamed:
            group = _group(key)
            names = sorted(n for n, g in renames.items() if g == group)
            lines.append("  {} (group '{}' is renamed to: {})".format(key, group, ", ".join(names)))
        error_msg = ("\n\nError: one or more parameters use a group renamed in the input "
                     "parameter files; use the new group name.\n\n" +
                     "\n".join(lines) + "\n\n")
        raise Exception(error_msg)

    if len(missing) > 0:
        error_msg = ("\n\nError: one or more parameters not found in input parameter files.\n\n" +
                     "Missing parameters: \n" +
                     "  " + ",".join(missing) + "\n\n" +
                     "Parameter files checked: \n" +
                     "\n".join(list(par_paths) + list(defaults_paths)) + "\n\n")
        raise Exception(error_msg)

    return refs


_TRUE = ('.true.', 'true', 't')
_FALSE = ('.false.', 'false', 'f')


def param_coerce(value, ref):
    """Convert a ``-p`` value to the type of the parameter's current value
    ``ref``: ``True``/``.true.``/``T`` (and the false forms) to a logical, an
    integer to a real, and a number to a string. Vectors are converted item by
    item. Anything else is returned unchanged.
    """
    if isinstance(value, list):
        item_ref = (ref[0] if ref else None) if isinstance(ref, list) else ref
        return [param_coerce(v, item_ref) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(ref, bool) and isinstance(value, str):
        if value.lower() in _TRUE:
            return True
        if value.lower() in _FALSE:
            return False
    elif isinstance(ref, float) and isinstance(value, int):
        return float(value)
    elif isinstance(ref, str) and isinstance(value, (int, float)):
        return str(value)
    return value


def group_pointers(defaults):
    """Parameters in ``defaults`` whose value names another defaults group, as
    ``{name: group}``; e.g. Yelmo's ``yelmo.nml_ydyn = "ydyn"`` gives
    ``{"nml_ydyn": "ydyn"}``.
    """
    groups = set(_group(k) for k in defaults)
    return {_name(key): val for key, val in defaults.items()
            if isinstance(val, str) and val in groups and val != _group(key)}


def group_renames(defaults, sources):
    """Find the groups renamed through a group pointer (see
    :func:`group_pointers`) set in ``sources``.

    Returns ``(renames, renamed)``: ``renames`` maps each new group name to its
    canonical defaults group (``nml_ydyn = "ydyn_north"`` gives
    ``{"ydyn_north": "ydyn"}``), and ``renamed`` holds the canonical groups
    used only under other names.
    """
    pointers = group_pointers(defaults)
    used = {}  # canonical group -> names it is used under
    for src in sources:
        for key, val in src.items():
            if _name(key) in pointers:
                used.setdefault(pointers[_name(key)], set()).add(val)
    renames = {name: group for group, names in used.items() for name in names if name != group}
    renamed = set(group for group, names in used.items() if group not in names)
    return renames, renamed


def param_assign_new(new, pars_src, par_paths):
    """Split new parameters by destination file: the file already holding the
    parameter's group, or the only file when the group is new.
    """
    inserts = [odict() for _ in pars_src]
    for key, val in new.items():
        group = _group(key)
        holders = [i for i, d in enumerate(pars_src) if any(_group(k) == group for k in d)]
        if not holders and len(pars_src) == 1:
            holders = [0]
        if len(holders) != 1:
            error_msg = ("\n\nError: cannot choose the parameter file to add {} to: ".format(key) +
                         "group '{}' is in {} of the input parameter files.\n\n".format(group, len(holders)) +
                         "Parameter files: \n" +
                         "\n".join(par_paths) + "\n\n")
            raise Exception(error_msg)
        inserts[holders[0]][key] = val
    return inserts


def param_insert(params, new):
    """Insert ``new`` parameters into ``params``, each after the last parameter
    of its group, or in a new group appended at the end. Keeping a group's
    parameters contiguous means it is written as a single namelist block.
    """
    new_by_group = odict()
    for key, val in new.items():
        new_by_group.setdefault(_group(key), odict())[key] = val

    last = {_group(key): key for key in params}

    out = odict()
    for key, val in params.items():
        out[key] = val
        group = _group(key)
        if last[group] == key and group in new_by_group:
            out.update(new_by_group.pop(group))
    for group_params in new_by_group.values():
        out.update(group_params)
    return out


def param_map_groups(params, grp_aliases):
    """Convert shortcut group names used on command line into actual groups that
    exist in parameter file using the mapping defined in the config file.
    """
    params_out = dict()

    for key, val in params.items():
        if '.' in key:
            tmp = key.split('.')
            grp = tmp[0]
            par = tmp[1]

            if grp in [*grp_aliases]:
                grp_new = grp_aliases[grp]
            else:
                grp_new = grp

            key_new = "{}.{}".format(grp_new, par)
        else:
            key_new = key

        params_out[key_new] = val

    return params_out
