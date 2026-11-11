"""Tests for ensemble submission as one Slurm job array (--array)."""
import argparse
import json
import os

import runme
from runme import ensemble
from runme.hpc import compress_indices, generate_array_jobscript, generate_jobscript
from runme.params import MultiParam, Param

TEMPLATE = os.path.join(os.path.dirname(runme.__file__), "templates", "submit_slurm")


def _member_script(omp=4):
    return generate_jobscript(TEMPLATE, "./exe par.nml", "job", "acc", "normal", None, "01:00:00",
                              "compute", omp, None, "", [], ())


def test_compress_indices():
    assert compress_indices([0, 1, 2, 5, 7, 8]) == "0-2,5,7-8"
    assert compress_indices([3]) == "3"
    assert compress_indices([2, 0, 1, 1]) == "0-2"


def test_array_script_per_runid():
    s = generate_array_jobscript(_member_script(), [0, 1, 2, 4], 2, per_runid=True)
    lines = s.split("\n")
    assert "#SBATCH --array=0-2,4%2" in lines
    assert "#SBATCH --output=./%a/out.out" in lines
    assert "#SBATCH --error=./%a/out.err" in lines
    assert "exec > out.out 2> out.err" not in s
    # every directive precedes the cd (sbatch ignores directives after the first command)
    icd = next(i for i, l in enumerate(lines) if l.startswith("cd "))
    assert all(not l.startswith("#SBATCH") for l in lines[icd:])
    assert lines.index("#SBATCH --array=0-2,4%2") < icd
    assert "srun --cpus-per-task=${SLURM_CPUS_PER_TASK:-1} ./exe par.nml" in s


def test_array_script_named_dirs():
    s = generate_array_jobscript(_member_script(omp=0), [0, 1], 0, per_runid=False)
    assert "#SBATCH --array=0-1" in s
    assert "#SBATCH --output=./array-%A_%a.out" in s
    assert "exec > out.out 2> out.err" in s


def _ctx(tmp_path, run):
    exe = tmp_path / "model.x"
    exe.write_text("#!/bin/sh\n")
    par = tmp_path / "par.nml"
    par.write_text("&ctl\n    a = 1\n/\n")
    info = {"par_path_as_argument": True, "files": [], "dir-special": {}, "links": [], "par_paths": {}, "grp_aliases": {},
            "par_defaults": [], "par_library": []}
    return argparse.Namespace(
        info=info, exe_path=str(exe), exe_alias=None, par_path=str(par), executable="./model.x par.nml",
        run=run, submit=True, dry_run=False, qos="normal", partition="compute", wall="01:00:00", mem=None,
        account="acc", omp=2, cpus=None, sbatch=[], jobname="job", email="", mail_type=[],
        template=TEMPLATE, array=3, command="runme test")


def test_ensemble_array_prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path, run=False)
    xparams = MultiParam([Param.parse("ctl.a=1,2,3")]).product()
    ensemble.run(ctx, xparams, {}, expdir=str(tmp_path / "ens"), indices=[0, 2])
    ens = tmp_path / "ens"
    assert (ens / "0" / "job.submit").is_file() and (ens / "2" / "job.submit").is_file()
    assert not (ens / "1").exists()
    assert (ens / "array.dirs").read_text().split("\n")[:2] == ["0 {}".format(ens / "0"), "2 {}".format(ens / "2")]
    assert "#SBATCH --array=0,2%3" in (ens / "array.submit").read_text()
    rec = json.loads((ens / "array.json").read_text())
    assert rec["status"] == "prepared" and rec["job_id"] is None
    assert json.loads((ens / "0" / "runme.json").read_text())["status"] == "prepared"


def test_ensemble_array_submitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path, run=True)
    calls = []

    def fake_submit(rundir, nm_jobscript="job.submit"):
        calls.append((rundir, nm_jobscript))
        return "Submitted batch job 4711"

    monkeypatch.setattr(runme.hpc, "submitjob", fake_submit)
    xparams = MultiParam([Param.parse("ctl.a=1,2")]).product()
    ensemble.run(ctx, xparams, {}, expdir=str(tmp_path / "ens"))
    ens = tmp_path / "ens"
    assert calls == [(str(ens), "array.submit")]           # one submission, not one per member
    assert json.loads((ens / "array.json").read_text())["job_id"] == "4711"
    assert json.loads((ens / "1" / "runme.json").read_text())["array_job"] == "4711_1"
