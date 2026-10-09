"""Tests for submit-script generation: --cpus and extra --sbatch directives."""
import os

import runme
from runme.hpc import generate_jobscript

TEMPLATE = os.path.join(os.path.dirname(runme.__file__), "templates", "submit_slurm")


def _script(omp=4, cpus=None, sbatch=(), mem=None):
    return generate_jobscript(TEMPLATE, "./exe", "job", "acc", "normal", mem, "01:00:00",
                              "compute", omp, cpus, "", [], sbatch)


def _directives(script):
    return [line for line in script.split("\n") if line.startswith("#SBATCH")]


def test_cpus_default_to_omp():
    s = _script(omp=4)
    assert "#SBATCH --cpus-per-task=4" in s
    assert "export OMP_NUM_THREADS=4 " in s
    assert "OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK" not in s


def test_cpus_independent_of_threads():
    s = _script(omp=2, cpus=128)
    assert "#SBATCH --cpus-per-task=128" in s
    assert "export OMP_NUM_THREADS=2 " in s
    assert "export MKL_NUM_THREADS=2" in s


def test_sbatch_directives_after_last_sbatch_line():
    s = _script(omp=1, sbatch=["--exclusive", "--mem=0"])
    d = _directives(s)
    assert d[-2:] == ["#SBATCH --exclusive", "#SBATCH --mem=0"]
    lines = s.split("\n")
    assert lines.index("#SBATCH --exclusive") == lines.index(d[-3]) + 1


def test_sbatch_without_omp_section():
    d = _directives(_script(omp=0, sbatch=["--mem-per-cpu=3940"]))
    assert d[-1] == "#SBATCH --mem-per-cpu=3940"
    assert not any("cpus-per-task" in line for line in d)
