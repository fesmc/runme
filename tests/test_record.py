"""Tests for the run record: the git revision is read before anything is done,
runme.json is written before the job is submitted, and a run directory whose
recorded job is still in the queue is refused."""
import argparse
import json
import os
import subprocess

import pytest

import runme
from runme.params import MultiParam, Param
from runme import ensemble
from runme import run as _run
from runme import stage as _stage

TEMPLATE = os.path.join(os.path.dirname(runme.__file__), "templates", "submit_slurm")


def test_git_revision_outside_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _stage.git_revision() == "Not under git version control."


def test_git_revision_without_git_stops(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(subprocess, "check_output", no_git)
    with pytest.raises(SystemExit) as exc:
        _stage.git_revision()
    assert "nothing was staged or submitted" in str(exc.value)


def _ctx(tmp_path, run=True):
    exe = tmp_path / "model.x"
    exe.write_text("#!/bin/sh\n")
    par = tmp_path / "par.nml"
    par.write_text("&ctl\n    a = 1\n/\n")
    info = {"par_path_as_argument": True, "files": [], "dir-special": {}, "links": [], "par_paths": {},
            "grp_aliases": {}, "par_defaults": [], "par_library": []}
    return argparse.Namespace(
        info=info, exe_path=str(exe), exe_alias=None, par_path=str(par), executable="./model.x par.nml",
        run=run, submit=True, dry_run=False, qos="normal", partition="compute", wall="01:00:00", mem=None,
        account="acc", omp=2, cpus=None, sbatch=[], jobname="job", email="", mail_type=[],
        template=TEMPLATE, command="runme test", git_hash="abc123", array=None)


def test_record_written_before_submit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path)
    rundir = str(tmp_path / "run")
    seen = {}

    def fake_submit(rundir, nm_jobscript="job.submit"):
        seen["record"] = json.loads(open(os.path.join(rundir, "runme.json")).read())
        return "Submitted batch job 4711"

    monkeypatch.setattr(runme.hpc, "submitjob", fake_submit)
    assert _run.execute_one(rundir, {}, ctx) == "submitted"
    assert seen["record"]["status"] == "staged" and seen["record"]["git_hash"] == "abc123"
    rec = json.loads(open(os.path.join(rundir, "runme.json")).read())
    assert rec["status"] == "submitted" and rec["job_id"] == "4711" and rec["git_hash"] == "abc123"


def _busy_rundir(path, job="4711"):
    path.mkdir(parents=True)
    (path / "runme.json").write_text(json.dumps({"status": "submitted", "job_id": job}))
    (path / "out.nc").write_text("output being written")


def test_refuses_rundir_with_queued_job(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path)
    _busy_rundir(tmp_path / "run")
    monkeypatch.setattr(runme.hpc, "queued_state", lambda job: "RUNNING" if job == "4711" else None)
    submitted = []
    monkeypatch.setattr(runme.hpc, "submitjob", lambda *a, **k: submitted.append(a))
    with pytest.raises(SystemExit) as exc:
        _run.execute_one(str(tmp_path / "run"), {}, ctx)
    assert "job 4711 (RUNNING)" in str(exc.value)
    assert not submitted and (tmp_path / "run" / "out.nc").is_file()   # nothing touched


def test_reuses_rundir_once_job_left_queue(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path)
    _busy_rundir(tmp_path / "run")
    monkeypatch.setattr(runme.hpc, "queued_state", lambda job: None)
    monkeypatch.setattr(runme.hpc, "submitjob", lambda *a, **k: "Submitted batch job 4712")
    assert _run.execute_one(str(tmp_path / "run"), {}, ctx) == "submitted"
    assert json.loads((tmp_path / "run" / "runme.json").read_text())["job_id"] == "4712"


def test_ensemble_refuses_before_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx = _ctx(tmp_path)
    _busy_rundir(tmp_path / "ens" / "1", job="4711_1")
    monkeypatch.setattr(runme.hpc, "queued_state", lambda job: "PENDING" if job == "4711_1" else None)
    xparams = MultiParam([Param.parse("ctl.a=1,2,3")]).product()
    with pytest.raises(SystemExit) as exc:
        ensemble.run(ctx, xparams, {}, expdir=str(tmp_path / "ens"))
    assert "job 4711_1 (PENDING)" in str(exc.value)
    assert not (tmp_path / "ens" / "params.txt").exists() and not (tmp_path / "ens" / "0").exists()
