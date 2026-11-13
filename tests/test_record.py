"""Tests for the run record: the git revision is read before anything is done, and
runme.json is written before the job is submitted."""
import argparse
import json
import os
import subprocess

import pytest

import runme
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


def test_record_written_before_submit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exe = tmp_path / "model.x"
    exe.write_text("#!/bin/sh\n")
    par = tmp_path / "par.nml"
    par.write_text("&ctl\n    a = 1\n/\n")
    info = {"par_path_as_argument": True, "files": [], "dir-special": {}, "links": [], "par_paths": {},
            "grp_aliases": {}, "par_defaults": [], "par_library": []}
    ctx = argparse.Namespace(
        info=info, exe_path=str(exe), exe_alias=None, par_path=str(par), executable="./model.x par.nml",
        run=True, submit=True, dry_run=False, qos="normal", partition="compute", wall="01:00:00", mem=None,
        account="acc", omp=2, cpus=None, sbatch=[], jobname="job", email="", mail_type=[],
        template=TEMPLATE, command="runme test", git_hash="abc123")
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
