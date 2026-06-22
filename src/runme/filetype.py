"""Parameter-file formats and extension-based dispatch.

A *format* is a :class:`FileType` subclass that converts between the on-disk
representation of a parameter file and runme's in-memory representation: a flat
``OrderedDict`` keyed ``"group.name"`` (e.g. ``"control.tau"``). One level of
grouping is the contract shared by every format -- a top-level table/group whose
keys are the parameters -- so a parameter set round-trips between formats.

Supported formats:

* :class:`~runme.namelist.Namelist` -- Fortran namelist (``.nml``, ``.par``).
* :class:`Toml` -- TOML (``.toml``); a ``[group]`` table with ``name = value``
  maps to ``group.name``.
* :class:`Json` -- JSON (``.json``); a ``{"group": {"name": value}}`` object
  maps to ``group.name``.
* :class:`LineSep` -- one ``group.name = value`` per line (``.jl``); each line is
  also a valid Julia field assignment, so the file ``include``s cleanly when the
  matching structs already exist.

:func:`filetype_for_path` chooses the format from a file's extension, so staging
reads and writes each parameter file in its own format.
"""
import os
import json as _json
from collections import OrderedDict as odict

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised on <3.11 only
    import tomli as _toml


class FileType(object):
    """Minimal parameter-file base: subclasses implement ``dumps``/``loads``.

    ``loads`` returns, and ``dumps`` accepts, a flat ``OrderedDict`` keyed
    ``"group.name"``.
    """

    def dumps(self, params):
        raise NotImplementedError()

    def loads(self, string):
        raise NotImplementedError()

    def dump(self, params, f):
        f.write(self.dumps(params))

    def load(self, f):
        return self.loads(f.read())


def _flatten_groups(data, sep, label):
    """Flatten a parsed ``{group: {name: value}}`` mapping to a flat
    ``{group<sep>name: value}`` :class:`OrderedDict`, enforcing exactly one
    level of grouping.
    """
    params = odict()
    for group, body in data.items():
        if not isinstance(body, dict):
            raise ValueError(
                "{} parameter files must group parameters under a table/object; "
                "found bare top-level key '{}'.".format(label, group))
        for name, value in body.items():
            if isinstance(value, dict):
                raise ValueError(
                    "{} parameter '{}{}{}' is a nested table/object; only one "
                    "level of grouping is supported.".format(
                        label, group, sep, name))
            params[group + sep + name] = value
    return params


def _split_longname(longname, sep, label):
    """Split a ``group<sep>name`` key into ``(group, name)``, enforcing exactly
    one level of grouping (the rule shared by every format).
    """
    parts = longname.split(sep)
    if len(parts) != 2 or "" in parts:
        raise ValueError(
            "{} expects 'group{}name' keys; got '{}'.".format(
                label, sep, longname))
    return parts[0], parts[1]


def _nest_groups(params, sep, label):
    """Invert :func:`_flatten_groups`: turn a flat ``{group<sep>name: value}``
    dict into ``{group: {name: value}}``, rejecting keys that are not exactly
    ``group<sep>name``.
    """
    nested = odict()
    for longname, value in params.items():
        group, name = _split_longname(longname, sep, label + " writer")
        nested.setdefault(group, odict())[name] = value
    return nested


class Toml(FileType):
    """TOML format: one level of tables mapped to ``group.name`` keys."""

    def __init__(self, sep='.'):
        self.sep = sep

    def loads(self, string):
        return _flatten_groups(_toml.loads(string), self.sep, "TOML")

    def dumps(self, params):
        nested = _nest_groups(params, self.sep, "TOML")
        blocks = []
        for group_name, body in nested.items():
            lines = ["[{}]".format(group_name)]
            for name, value in body.items():
                lines.append("{} = {}".format(name, _format_literal(value)))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) + "\n"


class Json(FileType):
    """JSON format: one level of objects mapped to ``group.name`` keys."""

    def __init__(self, sep='.'):
        self.sep = sep

    def loads(self, string):
        data = _json.loads(string)
        if not isinstance(data, dict):
            raise ValueError(
                "JSON parameter files must contain a top-level object.")
        return _flatten_groups(data, self.sep, "JSON")

    def dumps(self, params):
        nested = _nest_groups(params, self.sep, "JSON")
        return _json.dumps(nested, indent=2) + "\n"


def _format_literal(value):
    """Format a Python value as a scalar/array literal.

    The literal syntax (``true``/``false``, bare numbers, double-quoted strings,
    ``[a, b, c]`` arrays) is the subset shared by TOML and Julia, so the same
    formatter serves both the :class:`Toml` and :class:`LineSep` writers.
    """
    if isinstance(value, bool):  # before int: bool is an int subclass
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _format_string_literal(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_format_literal(v) for v in value) + "]"
    raise ValueError(
        "Cannot format value of type {} as a literal.".format(
            type(value).__name__))


def _format_string_literal(s):
    """Quote a string with double quotes, escaping the special characters that
    occur in parameter values (valid for both TOML basic strings and Julia).
    """
    escaped = (s.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t"))
    return '"{}"'.format(escaped)


def _parse_literal(token):
    """Parse a scalar or ``[...]`` array literal, reusing the namelist scalar
    parser (so ``.true.``, numbers, and quoted strings parse consistently).
    """
    from runme.namelist import _parse_value  # local: avoids an import cycle
    token = token.strip()
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1]
        items = [t for t in inner.split(",") if t.strip()]
        return [_parse_literal(t) for t in items]
    return _parse_value(token)


class LineSep(FileType):
    """Flat one-parameter-per-line format: ``group.name <assign> value``.

    Registered for ``.jl``: with the default ``assign=' = '`` each line is a
    valid Julia field assignment, so the file ``include``s cleanly once the
    matching structs exist. Lines are read by splitting on the first ``=``
    (alignment whitespace is ignored); values are written with
    :func:`_format_literal` and read with :func:`_parse_literal`. Blank lines and
    ``#`` comments (whole-line or trailing, as in namelist) are ignored.
    """

    def __init__(self, assign=" = ", sep="."):
        self.assign = assign
        self.sep = sep

    def loads(self, string):
        params = odict()
        for raw in string.split("\n"):
            line = raw.strip()
            if "#" in line:  # strip comments (naive, like namelist's '!')
                line = line[:line.index("#")].strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(
                    "Cannot parse .jl line (no '='): {!r}".format(raw))
            key, _, val = line.partition("=")
            key = key.strip()
            _split_longname(key, self.sep, "Julia (.jl)")  # validate group.name
            params[key] = _parse_literal(val)
        return params

    def dumps(self, params):
        lines = []
        for longname, value in params.items():
            _split_longname(longname, self.sep, "Julia (.jl) writer")  # validate
            lines.append("{}{}{}".format(
                longname, self.assign, _format_literal(value)))
        return "\n".join(lines) + "\n"


# Extensions runme recognises as parameter files, by format.
NAMELIST_EXTENSIONS = (".nml", ".par")
TOML_EXTENSIONS = (".toml",)
JSON_EXTENSIONS = (".json",)
LINESEP_EXTENSIONS = (".jl",)
PARAM_EXTENSIONS = (NAMELIST_EXTENSIONS + TOML_EXTENSIONS
                    + JSON_EXTENSIONS + LINESEP_EXTENSIONS)


def filetype_for_path(path):
    """Return a :class:`FileType` instance chosen from ``path``'s extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in NAMELIST_EXTENSIONS:
        from runme.namelist import Namelist  # local: avoids an import cycle
        return Namelist()
    if ext in TOML_EXTENSIONS:
        return Toml()
    if ext in JSON_EXTENSIONS:
        return Json()
    if ext in LINESEP_EXTENSIONS:
        return LineSep()
    raise ValueError(
        "Unsupported parameter-file extension '{}' for path '{}'. "
        "Supported: {} (namelist), {} (toml), {} (json), {} (julia).".format(
            ext or "(none)", path,
            ", ".join(NAMELIST_EXTENSIONS), ", ".join(TOML_EXTENSIONS),
            ", ".join(JSON_EXTENSIONS), ", ".join(LINESEP_EXTENSIONS)))
