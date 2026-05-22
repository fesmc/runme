"""Ensemble sampling for runme.

Generates ensemble parameter sets:

* ``product``      -- factorial combination of discrete values
* ``lhs``          -- Latin-hypercube sampling (our own implementation, vendored)
* ``monte_carlo``  -- basic Monte-Carlo sampling

Backs the ``runme sample`` and ``runme product`` subcommands. Vendored in
Phase 3 from ``runner.lib.doelhs`` and the ``MultiParam`` sampling methods.
"""
