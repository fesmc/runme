"""HPC submission helpers for runme.

Covers everything related to running or submitting a staged run directory:

* resolve a queue alias to (qos, partition, wall)
* render a SLURM job script from a template
* run a job in the background
* submit a job to the queue via sbatch

Populated in Phase 2 by moving ``runjob`` / ``submitjob`` / ``preparejob`` /
``generate_jobscript`` out of the existing script.
"""
