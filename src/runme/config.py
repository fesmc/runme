"""Configuration loading for runme.

Resolves and loads the project configuration files:

* ``.runme_config``               -- local, per-host settings (hpc, account, omp, email)
* ``.runme/<model>_info.json``    -- executables, parameter files, links, copies
* queues definition               -- HPC queue aliases (qos, partition, wall)
* SLURM submit templates          -- job-script templates

Phase 5 introduces the lookup chain: project ``.runme/`` -> ``~/.config/runme/``
-> packaged ``templates/`` defaults. Populated in Phase 2 (move) and Phase 5
(fallback chain).
"""
