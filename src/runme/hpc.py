"""HPC submission helpers for runme.

Covers resolving a queue alias to concrete SLURM settings, rendering a job
script from a template, running a job in the background, and submitting a job
to the queue via sbatch.

Moved verbatim (modulo formatting) from the historical runme script.
"""
import sys
import subprocess as subp


def resolve_queue(hpc_queues, hpc_config, queue, qos, partition, wall, mem):
    """Resolve SLURM queue settings for a submitted job.

    Individual ``--qos`` / ``--part`` / ``--wall`` options override the alias.
    When any of them is missing, the values are populated from the named queue
    alias. Memory falls back to the ``mem`` value in ``hpc_config`` if set.

    Returns ``(qos, partition, wall, mem)``.
    """
    if wall is None or qos is None or partition is None:
        if queue is None:
            error_msg = ("At least the queue alias QUEUE, or all inidividual queue options "
                         "(WALL,QOS,PARTITION) must be specified. See help (-h) for details.")
            raise Exception(error_msg)

        # Populate queue options from alias as needed
        if qos is None:
            qos = hpc_queues["queues"][queue]["qos"]
        if partition is None:
            partition = hpc_queues["queues"][queue]["partition"]
        if wall is None:
            wall = hpc_queues["queues"][queue]["wall"]

    # Set memory option if not set at command line and available. Since memory
    # is job specific, a default value can be set in hpc_config rather than in
    # hpc_queues.
    if mem is None and "mem" in hpc_config.keys():
        mem = hpc_config["mem"]

    return qos, partition, wall, mem


def runjob(rundir, cmd, omp):
    """Run a staged job in the background."""
    if omp > 0:
        cmd_job = "cd {} && export OMP_NUM_THREADS={} && {} > {} &".format(rundir, omp, cmd, "out.out")
    else:
        cmd_job = "cd {} && exec {} > {} &".format(rundir, cmd, "out.out")

    print("Running job in background: {}".format(cmd_job))

    # Run the command (ie, change to output directory and run job).
    # `shell=True` can be a security hazard but is acceptable in this context;
    # see https://docs.python.org/3/library/subprocess.html#frequently-used-arguments
    try:
        jobstatus = subp.Popen(
            cmd_job,
            shell=True,
            stdin=subp.DEVNULL,
            stdout=subp.DEVNULL,
            stderr=subp.DEVNULL,
            start_new_session=False,
        )
    except subp.CalledProcessError as error:
        print(error)
        sys.exit()

    return jobstatus


def preparejob(path_template, rundir, cmd, qos, mem, wall, partition, account, omp, jobname, email, mail_type):
    """Prepare and write a job script for submitting a job to a HPC queue."""
    nm_jobscript = 'job.submit'
    path_jobscript = "{}/{}".format(rundir, nm_jobscript)

    script = generate_jobscript(path_template, cmd, jobname, account, qos, mem, wall, partition, omp, email, mail_type)
    open(path_jobscript, 'w').write(script)

    return


def submitjob(rundir):
    """Submit a job to a HPC queue (sbatch) with a template job script."""
    nm_jobscript = 'job.submit'
    cmd_job = "cd {} && sbatch {}".format(rundir, nm_jobscript)

    try:
        out = subp.check_output(cmd_job, shell=True, stderr=subp.STDOUT)
        jobstatus = out.decode("utf-8").strip()
        print(jobstatus)
    except subp.CalledProcessError as error:
        print(error)
        sys.exit()

    return jobstatus


def generate_jobscript(template, cmd, jobname, account, qos, mem, wall, partition, omp, email, mail_type):
    """Build the job script from a template file, substituting ``< >`` fields."""
    # If omp has been set, generate a jobscript string with appropriate settings
    if omp > 0:
        omp_script = open(template + "_omp", 'r').read()
        omp_script = omp_script.replace('<OMP>', "{}".format(omp))
    else:
        omp_script = ""

    # Email settings
    if not email == "":
        email_script = "#SBATCH --mail-user=<EMAIL>".replace('<EMAIL>', email)
        for mt in mail_type:
            email_script = email_script + "\n" + "#SBATCH --mail-type=<MT>".replace('<MT>', mt)
    else:
        email_script = ""

    # Read in jobscript template
    job_script = open(template, 'r').read()

    job_script = job_script.replace('<EMAILSECTION>', email_script)
    job_script = job_script.replace('<OMPSECTION>', omp_script)
    job_script = job_script.replace('<PARTITION>', partition)
    job_script = job_script.replace('<QOS>', qos)
    job_script = job_script.replace('<WALL>', "{}".format(wall))
    job_script = job_script.replace('<OMP>', "{}".format(omp))
    job_script = job_script.replace('<JOBNAME>', jobname)
    job_script = job_script.replace('<ACCOUNT>', account)
    job_script = job_script.replace('<CMD>', cmd)

    if mem is None or mem == -1:
        job_script = job_script.replace('#SBATCH --mem=<MEM>', "")
    else:
        job_script = job_script.replace('<MEM>', "{}".format(mem))

    return job_script
