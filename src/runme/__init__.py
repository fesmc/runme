"""runme: stage, run, and submit single simulations and ensembles.

This package consolidates the project-level ``runme`` script with the minimum
ensemble functionality previously provided by the ``runner`` package, so that
``runme`` is the single tool needed in model projects.

Module map (filled in over the migration phases):

* ``cli``      -- argparse entrypoint and dispatch (single-sim / ensemble / sample)
* ``config``   -- load ``.runme_config``, ``.runme/<model>_info.json``, queues
* ``stage``    -- run-directory setup: copy exe, parameter files, links; write records
* ``hpc``      -- queue resolution, SLURM template rendering, run/submit helpers
* ``ensemble`` -- ensemble orchestration: build parameter sets, iterate members
* ``params``   -- parameter parsing and the parameter matrix (vendored from runner)
* ``dist``     -- distribution specs for continuous sampling (vendored from runner)
* ``sample``   -- factorial product, Latin-hypercube, and Monte-Carlo sampling
* ``namelist`` -- Fortran namelist read/write (vendored from runner.ext.namelist)
"""

__version__ = "0.5.0"
