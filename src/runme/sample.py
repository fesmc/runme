"""Latin-hypercube sampling for runme ensembles.

The ``lhs`` routine is vendored from ``runner.lib.doelhs`` (itself derived from
pyDOE / scidoe). It is a self-contained numerical routine with no dependency on
the rest of runme, so :mod:`runme.params` can use it without an import cycle.

The factorial ``product`` and ``monte_carlo`` strategies live as methods on
:class:`runme.params.MultiParam`. The user-facing ``runme sample`` / ``runme
product`` subcommands are wired up in Phase 4.

Original copyright (scidoe / pyDOE):
    Copyright (C) 2012-2013 Michael Baudin; 2012 Maria Christopoulou;
    2010-2011 INRIA - Michael Baudin; 2009 Yann Collette;
    2009 CEA - Jean-Marc Martinez. Converted to Python by Abraham Lee.
    Copied by M. Perrette from
    https://github.com/tisimst/pyDOE/blob/master/pyDOE/doe_lhs.py
"""
import numpy as np

__all__ = ['lhs']


def lhs(n, samples=None, criterion=None, iterations=None):
    """Generate a Latin-hypercube design.

    Parameters
    ----------
    n : int
        The number of factors to generate samples for.
    samples : int, optional
        The number of samples to generate for each factor (default: ``n``).
    criterion : str, optional
        One of "center"/"c", "maximin"/"m", "centermaximin"/"cm",
        "correlate"/"corr". If not given, the design is simply randomized.
    iterations : int, optional
        Iterations for the maximin/correlate algorithms (default: 5).

    Returns
    -------
    H : 2d-array
        An ``n``-by-``samples`` design matrix normalized to ``[0, 1]``.
    """
    H = None

    if samples is None:
        samples = n

    if criterion is not None:
        assert criterion.lower() in ('center', 'c', 'maximin', 'm',
                                     'centermaximin', 'cm', 'correlation',
                                     'corr'), 'Invalid value for "criterion": {}'.format(criterion)
    else:
        H = _lhsclassic(n, samples)

    if criterion is None:
        criterion = 'center'

    if iterations is None:
        iterations = 5

    if H is None:
        if criterion.lower() in ('center', 'c'):
            H = _lhscentered(n, samples)
        elif criterion.lower() in ('maximin', 'm'):
            H = _lhsmaximin(n, samples, iterations, 'maximin')
        elif criterion.lower() in ('centermaximin', 'cm'):
            H = _lhsmaximin(n, samples, iterations, 'centermaximin')
        elif criterion.lower() in ('correlate', 'corr'):
            H = _lhscorrelate(n, samples, iterations)

    return H


def _lhsclassic(n, samples):
    # Generate the intervals
    cut = np.linspace(0, 1, samples + 1)

    # Fill points uniformly in each interval
    u = np.random.rand(samples, n)
    a = cut[:samples]
    b = cut[1:samples + 1]
    rdpoints = np.zeros_like(u)
    for j in range(n):
        rdpoints[:, j] = u[:, j] * (b - a) + a

    # Make the random pairings
    H = np.zeros_like(rdpoints)
    for j in range(n):
        order = np.random.permutation(range(samples))
        H[:, j] = rdpoints[order, j]

    return H


def _lhscentered(n, samples):
    # Generate the intervals
    cut = np.linspace(0, 1, samples + 1)

    # Fill points uniformly in each interval
    u = np.random.rand(samples, n)
    a = cut[:samples]
    b = cut[1:samples + 1]
    _center = (a + b) / 2

    # Make the random pairings
    H = np.zeros_like(u)
    for j in range(n):
        H[:, j] = np.random.permutation(_center)

    return H


def _lhsmaximin(n, samples, iterations, lhstype):
    maxdist = 0

    # Maximize the minimum distance between points
    for i in range(iterations):
        if lhstype == 'maximin':
            Hcandidate = _lhsclassic(n, samples)
        else:
            Hcandidate = _lhscentered(n, samples)

        d = _pdist(Hcandidate)
        if maxdist < np.min(d):
            maxdist = np.min(d)
            H = Hcandidate.copy()

    return H


def _lhscorrelate(n, samples, iterations):
    mincorr = np.inf

    # Minimize the components correlation coefficients
    for i in range(iterations):
        Hcandidate = _lhsclassic(n, samples)
        R = np.corrcoef(Hcandidate)
        if np.max(np.abs(R[R != 1])) < mincorr:
            mincorr = np.max(np.abs(R - np.eye(R.shape[0])))
            print('new candidate solution found with max,abs corrcoef = {}'.format(mincorr))
            H = Hcandidate.copy()

    return H


def _pdist(x):
    """Calculate the pair-wise point distances of a matrix."""
    x = np.atleast_2d(x)
    assert len(x.shape) == 2, 'Input array must be 2d-dimensional'

    m, n = x.shape
    if m < 2:
        return []

    d = []
    for i in range(m - 1):
        for j in range(i + 1, m):
            d.append((sum((x[j, :] - x[i, :]) ** 2)) ** 0.5)

    return np.array(d)
