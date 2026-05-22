"""Run-directory staging for runme.

Creates a run directory and populates it ready for execution:

* copy the executable
* copy the relevant parameter files (filtered by executable alias)
* copy any extra files and special directories
* create symlinks to input data folders
* write per-rundir records (``runme.json`` and the ``params.txt`` / ``info.txt``
  text tables)

This is shared by both the single-simulation and ensemble paths so that every
run directory is self-describing in the same way. Populated in Phase 2 (move
the existing helpers) and Phase 4 (per-rundir text tables).
"""
