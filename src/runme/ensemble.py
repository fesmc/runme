"""Ensemble orchestration for runme.

Builds the ensemble parameter set (from inline ``-p`` sweeps, the ``sample`` /
``product`` subcommands, or an ``-i`` parameter file), then iterates over the
selected members, staging and optionally running/submitting each.

Output-file layout (Phase 4):

* expdir: ``params.txt`` / ``info.txt``           -- all params (permuted + fixed)
* expdir: ``params_ensemble.txt`` / ``info_ensemble.txt`` -- permuted subset only
* each member rundir: ``params.txt`` / ``info.txt`` (single row, all params)
  plus ``runme.json`` (full record)

Member selection honours the ``-j`` slurm-array index syntax. Populated in
Phase 4.
"""
