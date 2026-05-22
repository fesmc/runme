"""Distribution specs for ensemble parameters.

Vendored and stripped from ``runner.tools.dist`` (and ``runner.tools.misc``).
Python 3 only. Keeps the command-line parsing needed to specify ensemble
dimensions:

* discrete values     ``a=1,2,3``        -> :class:`DiscreteDist`
* discrete range      ``a=0:10:5``       -> :class:`DiscreteDist`
* uniform             ``a=U?0,1``        -> scipy ``uniform``
* normal              ``a=N?0,1``        -> scipy ``norm``
* any scipy dist      ``a=TYPE?ARG,...`` -> scipy distribution

Dropped: the Bayesian-only helpers (``cost``, ``dummydist``, the
``dist_todict``/``dist_fromkw`` serialization used by ``Param.as_dict``).
"""
import numpy as np


def parse_val(s):
    "string to int, float, or str"
    try:
        val = int(s)
    except ValueError:
        try:
            val = float(s)
        except ValueError:
            val = s
    return val


class LazyDist(object):
    "lazy loading of scipy distributions"

    def __init__(self, name):
        self.name = name

    def __call__(self, *args, **kwargs):
        import scipy.stats.distributions
        dist = getattr(scipy.stats.distributions, self.name)
        return dist(*args, **kwargs)


norm = LazyDist('norm')
uniform = LazyDist('uniform')


# string -> values / distribution
# -------------------------------
def parse_list(string):
    """List of parameters: VALUE[,VALUE,...]"""
    if not string:
        raise ValueError("empty list")
    return [parse_val(value) for value in string.split(',')]


def parse_range(string):
    """Parameter range: START:STOP:N"""
    start, stop, n = string.split(':')
    start = float(start)
    stop = float(stop)
    n = int(n)
    return np.linspace(start, stop, n).tolist()


def parse_dist(string):
    """Distribution: ``N?MEAN,STD`` or ``U?MIN,MAX`` or ``TYPE?ARG1[,ARG2 ...]``
    where TYPE is any scipy.stats distribution with ``*shp, loc, scale`` params.
    """
    name, spec = string.split('?')
    args = [float(a) for a in spec.split(',')]

    if name == "N":
        mean, std = args
        dist = norm(mean, std)
    elif name == "U":
        lo, hi = args  # note: uniform?loc,scale differs!
        dist = uniform(lo, hi - lo)
    else:
        dist = LazyDist(name)(*args)

    return dist


class DiscreteDist(object):
    """Prior parameter that takes a number of discrete values."""

    def __init__(self, values):
        self.values = np.asarray(values)

    def rvs(self, size):
        indices = np.random.randint(0, len(self.values), size)
        return self.values[indices]

    def ppf(self, q, interpolation='nearest'):
        return np.percentile(self.values, q * 100, interpolation=interpolation)

    def __str__(self):
        return ",".join(*[str(v) for v in self.values])

    @classmethod
    def parse(cls, string):
        if ':' in string:
            values = parse_range(string)
        else:
            values = parse_list(string)
        return cls(values)


def parse_dist2(string):
    """Parse a spec into a distribution: ``?`` => continuous, else discrete."""
    if '?' in string:
        return parse_dist(string)
    else:
        return DiscreteDist.parse(string)


# distribution -> string (for human-readable parameter summaries)
# ---------------------------------------------------------------
def dist_to_str(dist):
    """Format a scipy-dist distribution as ``TYPE?ARG,...``."""
    dname = dist.dist.name
    dargs = dist.args

    # shortened notation
    dname = dname.replace("norm", "N")
    if dname == "uniform":
        dname = "U"
        loc, scale = dargs
        dargs = loc, loc + scale  # more natural

    sargs = ",".join([str(v) for v in dargs])
    return "{}?{}".format(dname, sargs)


def dist_to_str2(dist):
    if isinstance(dist, DiscreteDist):
        return str(dist)
    else:
        return dist_to_str(dist)
