"""Ensemble parameters and the parameter matrix.

Vendored and stripped from ``runner.param``, ``runner.xparams`` and
``runner.tools.frame``. Python 3 only. Provides:

* :class:`Param` / :class:`DiscreteParam` -- parse ``NAME=SPEC`` specifications
* :class:`MultiParam` -- combine parameters; ``product`` / ``sample_lhs`` /
  ``sample_montecarlo`` to build an ensemble
* :class:`XParams` -- the parameter matrix written to / read from ``params.txt``
* :func:`str_dataframe` / :class:`DataFrame` -- minimal fixed-width table I/O,
  preserving the historical ``params.txt`` format

Dropped: the Bayesian machinery (``ScipyParam``, ``FrozenParam(s)``, likelihood
/ cost, ``as_dict`` / ``fromkw`` serialization, and ``XParams.resample``).
"""
import logging
import itertools
from collections import OrderedDict as odict

import numpy as np

from runme.dist import parse_dist2, dist_to_str2, DiscreteDist

# default criterion for the lhs method
LHS_CRITERION = 'centermaximin'


# ---------------------------------------------------------------------------
# Minimal fixed-width table I/O (vendored from runner.tools.frame)
# ---------------------------------------------------------------------------
def str_dataframe(pnames, pmatrix, max_rows=int(1e20), include_index=False, index=None):
    """Pretty-print a matrix like pandas, using only basic python."""
    col_width_default = 6
    col_fmt = []
    col_width = []
    for p in pnames:
        w = max(col_width_default, len(p))
        col_width.append(w)
        col_fmt.append("{:>" + str(w) + "}")

    if include_index:
        idx_w = len(str(len(pmatrix) - 1))  # width of last line index
        idx_fmt = "{:<" + str(idx_w) + "}"  # aligned left
        col_fmt.insert(0, idx_fmt)
        pnames = [""] + list(pnames)
        col_width = [idx_w] + col_width

    line_fmt = " ".join(col_fmt)
    header = line_fmt.format(*pnames)

    lines = []
    for i, pset in enumerate(pmatrix):
        if include_index:
            ix = i if index is None else index[i]
            pset = [ix] + list(pset)
        lines.append(line_fmt.format(*pset))

    n = len(lines)
    if n <= max_rows:
        return "\n".join([header] + lines)
    else:
        sep = line_fmt.format(*['.' * min(3, w) for w in col_width])
        return "\n".join([header] + lines[:max_rows // 2] + [sep] + lines[-max_rows // 2:])


def read_dataframe(pfile):
    header = open(pfile).readline().strip()
    if header.startswith('#'):
        header = header[1:]
    pnames = header.split()
    pvalues = np.loadtxt(pfile, skiprows=1)
    if np.ndim(pvalues) == 1:
        pvalues = pvalues[:, None]
    return pnames, pvalues


class DataFrame(object):
    """Names + value matrix, with fixed-width text I/O."""

    def __init__(self, values, names):
        self.values = values
        self.names = names

    @classmethod
    def read(cls, pfile):
        names, values = read_dataframe(pfile)
        return cls(values, names)

    def write(self, pfile):
        with open(pfile, "w") as f:
            f.write(str(self))

    def __getitem__(self, k):
        return self.values[:, self.names.index(k)]

    def keys(self):
        return self.names

    def __str__(self):
        return str_dataframe(self.names, self.values, index=self.index)

    @property
    def size(self):
        return len(self.values)

    def __iter__(self):
        for k in self.names:
            yield k

    @property
    def shape(self):
        return self.values.shape

    @property
    def index(self):
        return np.arange(self.size)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
class Param(object):
    """A parameter as a (named) random variable / value spec."""

    def __init__(self, name, default=None, dist=None, help=None, full_name=None):
        self.name = name
        self.dist = dist
        self.default = default
        self.help = help
        self.full_name = full_name

    def __call__(self, value=None):
        raise NotImplementedError("frozen parameters are not used in runme")

    def __str__(self):
        if self.dist:
            return "{name}={dist}".format(name=self.name, dist=dist_to_str2(self.dist))
        else:
            return "{name}={default}".format(name=self.name, default=self.default)

    def __eq__(self, other):
        return (isinstance(other, Param) and self.name == other.name) \
            or (isinstance(other, str) and self.name == other)

    @classmethod
    def parse(cls, string):
        """Parse a ``NAME=SPEC`` parameter definition.

        SPEC specifies values or a distribution:

        * discrete values   ``VALUE[,VALUE...]``
        * range              ``START:STOP:N``
        * distribution       ``TYPE?ARG,ARG[,...]`` (``U?min,max``, ``N?mean,sd``,
          or any scipy.stats distribution as ``TYPE?[SHP,]LOC,SCALE``)

        An optional default may be appended with ``!DEFAULT``.
        """
        try:
            name, spec = string.split('=')
            if '!' in spec:
                from runme.dist import parse_val
                spec, default = spec.split('!')
                default = parse_val(default)
            else:
                default = None
            dist = parse_dist2(spec)
            return cls(name, dist=dist, default=default)
        except Exception as error:
            logging.error(str(error))
            raise


class DiscreteParam(Param):
    def __init__(self, *args, **kwargs):
        super(DiscreteParam, self).__init__(*args, **kwargs)
        if not isinstance(self.dist, DiscreteDist):
            raise TypeError("expected DiscreteDist, got: " + type(self.dist).__name__)


def filterkeys(kwargs, keys):
    return {k: kwargs[k] for k in kwargs if k in keys}


class ParamList(list):
    """Enhanced list of Param instances; pure data structure."""

    def __init__(self, params):
        super(ParamList, self).__init__(params)
        for p in self:
            if not hasattr(p, 'name'):
                raise TypeError("Param-like with 'name' attribute required, got:" + repr(type(p)))

    @property
    def names(self):
        return [p.name for p in self]

    def __getitem__(self, name):
        if type(name) is int:
            return list.__getitem__(self, name)
        else:
            return {p.name: p for p in self}[name]

    def __add__(self, other):
        return type(self)(list(self) + list(other))


class MultiParam(ParamList):
    """Combine a list of parameters; sample or take their factorial product."""

    def product(self):
        for p in self:
            if not isinstance(p.dist, DiscreteDist):
                raise TypeError("cannot make product of continuous distributions: " + p.name)
        return XParams(list(itertools.product(*[p.dist.values.tolist() for p in self])), self.names)

    def sample_montecarlo(self, size, seed=None):
        """Basic Monte-Carlo sampling -> XParams."""
        pmatrix = np.empty((size, len(self.names)))
        for i, p in enumerate(self):
            pmatrix[:, i] = p.dist.rvs(size=size, random_state=seed + i if seed else None)
        return XParams(pmatrix, self.names)

    def sample_lhs(self, size, seed=None, criterion=LHS_CRITERION, iterations=None):
        """Latin-hypercube sampling -> XParams."""
        # Local import avoids any import cycle with runme.sample.
        from runme.sample import lhs

        pmatrix = np.empty((size, len(self.names)))
        np.random.seed(seed)
        lhd = lhs(len(self.names), size, criterion, iterations)  # all in [0, 1]
        for i, p in enumerate(self):
            pmatrix[:, i] = p.dist.ppf(lhd[:, i])  # quantile for this distribution
        return XParams(pmatrix, self.names)

    def sample(self, size, seed=None, method="lhs", **kwargs):
        """Dispatch to a sampling method. Unused **kwargs are ignored."""
        if method == "lhs":
            opts = filterkeys(kwargs, ['criterion', 'iterations'])
            return self.sample_lhs(size, seed, **opts)
        else:
            return self.sample_montecarlo(size, seed)


# ---------------------------------------------------------------------------
# Parameter matrix
# ---------------------------------------------------------------------------
class XParams(DataFrame):
    """Ensemble parameters: a value matrix with named columns."""

    def __init__(self, values, names, default=None):
        self.values = values
        self.names = names
        self.default = default

    def pset_as_array(self, i=None):
        if i is None:
            pvalues = self.default
        else:
            pvalues = self.values[i]
        if hasattr(pvalues, 'tolist'):
            pvalues = pvalues.tolist()  # numpy array
        return pvalues

    def pset_as_dict(self, i=None):
        """Return parameter set ``i`` as an ordered dict."""
        pvalues = self.pset_as_array(i)
        if pvalues is None:
            return odict()  # default parameters not provided
        params = odict()
        for k, v in zip(self.names, pvalues):
            params[k] = v
        return params
