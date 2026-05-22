"""Fortran namelist read/write.

Vendored from ``runner.ext.namelist`` (originally adapted from
https://github.com/leifdenby/namelist_python). Python 3 only; the
``runner.filetype.FileType`` base is inlined here as :class:`FileType` so the
module has no dependency on the runner package.

The public helpers used by runme are :func:`param_write_to_files` (write a dict
of ``group.name`` parameters into one or more namelist files) and the
:class:`Namelist` format itself.
"""
from collections import OrderedDict as odict
import re
from itertools import groupby


class FileType(object):
    """Minimal parameter-file base: subclasses implement ``dumps``/``loads``."""

    def dumps(self, params):
        raise NotImplementedError()

    def loads(self, string):
        raise NotImplementedError()

    def dump(self, params, f):
        f.write(self.dumps(params))

    def load(self, f):
        return self.loads(f.read())


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


def param_write_to_files(params, nml_src_paths, nml_dst_paths, grp_aliases=None):
    """Write parameters from a dict to one or more destination parameter files,
    given the input parameter file(s), substituting group names by their aliases
    when necessary.
    """
    # First expand input parameter group-name aliases if available
    if grp_aliases is not None and len(grp_aliases) > 0:
        params_mapped = param_map_groups(params, grp_aliases)
    else:
        params_mapped = params

    # Next, check to make sure desired parameters exist
    param_check_all(params_mapped, nml_src_paths)

    # If everything was ok, loop over files and write new parameter values
    for par_src_path, par_dst_path in zip(nml_src_paths, nml_dst_paths):
        param_write_to_file(params_mapped, par_src_path, par_dst_path)

    return


def param_check_all(params, par_paths):
    """Check whether all parameters defined in a dict exist in one or more input
    namelist parameter files.
    """
    # Get all possible parameters from input files
    params_all = []
    for path in par_paths:
        params_all.append(Namelist().load(open(path)))

    # Extract set of keys from all files
    all_keys = set(k for d in params_all for k in d)

    # Determine which keys do not exist in parameter file params
    missing_keys = set(params) - set(all_keys)

    if len(missing_keys) > 0:
        error_msg = ("\n\nError: one or more parameters not found in input parameter files.\n\n" +
                     "Missing parameters: \n" +
                     "  " + ",".join(missing_keys) + "\n\n" +
                     "Parameter files checked: \n" +
                     "\n".join(par_paths) + "\n\n")
        raise Exception(error_msg)


def param_write_to_file(params, par_src_path, par_dst_path):
    """Load parameters from a namelist parameter file, update values according to
    the dictionary provided, and then write the updated namelist parameter file.
    """
    # Load input namelist parameters
    params_now = Namelist().load(open(par_src_path))

    # Update parameters with desired values (only update parameter values if the
    # parameters are defined in this set)
    params_now = nml_update_if_exists(params_now, params)

    # Write updated parameter file to rundir
    f = open(par_dst_path, 'w')
    Namelist().dump(params_now, f)

    return


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
