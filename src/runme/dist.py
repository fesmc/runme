"""Distribution specs for continuous sampling (vendored from runner).

Parses command-line distribution specifications such as ``U?0,1`` (uniform) and
``N?0,1`` (normal), backed by scipy distributions, for use by Latin-hypercube
and Monte-Carlo sampling.

Vendored and stripped in Phase 3 from ``runner.tools.dist`` (keeping the
parsing / scipy-backed pieces; dropping cost and the v1 helpers).
"""
