"""Parameter parsing and the parameter matrix (vendored from runner).

Provides the minimum needed to specify and store ensemble parameters:

* parse ``NAME=SPEC`` specs, where SPEC is a single value, a comma list, a
  ``START:STOP:N`` range, or a distribution (see :mod:`runme.dist`)
* the parameter matrix used to write/read ``params.txt``

Vendored and stripped (Python 3 only; no resample/Bayesian machinery) in
Phase 3 from ``runner.param`` and ``runner.xparams``.
"""
