# runme

`runme` is a general script to perform all preiminary steps needed to run a program, and then to run it.
In fact, it is almost too simple. But we have found it useful in many contexts so it seemed worth it to make it available and general to facilitate any further development.
`runme` is written in Python and makes use of a couple of JSON configuration files to make it extensible.

## How to get started

First copy the `runme` script and the `.runme` configuration directory to your model directory, where you would like to launch simulations from:

```
cp runme $MODEL_PATH/
cp -r .runme $MODEL_PATH/
```

Next modify the choices in the file `$MODEL_PATH/.runme/my_model_info.json`, which describe names of executables, folders to be copied/linked to run directories, parameter files to be copied, etc.

Finally, copy the user configuration file to the main directory and enter the name of the HPC you are using, your email address etc.:

```
cd $MODEL_PATH
cp .runme/runme_config .runme_config
```

That's it! `runme` should now be ready for use with your model. Note:

- If you will use a new HPC that is not listed in `.runme/queues.json`, then please add it to the file together with relevant settings for the different job queues available. Please add it as an issue here, so that the repository can be continuously updated with new HPC information.
- You can make your own job submission templates in `.runme/` (see `submit_slurm` and `submit_slurm_omp`) if something specific is needed for your HPC and/or model. To use a custom job submission templates, make sure to point to them in the `.runme/queues.json` options.
 
## Basic uses

Once an executable has been created, you can prepare an experiment and run it using the included Python job submission script `runme`. The following steps are carried out via the script:

1. The run directory directory is created.
2. The executable is copied to the run directory.
3. The relevant parameter files are copied to the run directory.
4. Links to the input data paths are created in the run directory.
5. The executable is run from the run directory, either as a background process or it is submitted to a queue via sbatch (the SLURM workload manager).

Importantly, it is possible to modify parameters in a parameter file inline via the option -p KEY=VAL [KEY=VAL ...]. The modified parameters will be written to the file stored in the run directory.

## Ensembles

Ensembles of simulations can be performed by calling `runme` via the Python module `runner`, which is designed for generating and managing ensembles. To install `runner` and its dependency `tabulate`, simply run the following:

```
pip install https://github.com/alex-robinson/runner/archive/refs/heads/master.zip
pip install tabulate
```

#### Using `jobrun` with `runme`

`jobrun` is a command that is part of the Python `runner` library, found here:
[https://github.com/alex-robinson/runner](https://github.com/alex-robinson/runner). This command facilitates running ensembles of simulations, or simulations with modified parameters via a convenient command-line interface. See the above `runner` page for its installation instructions.

using `jobrun`, the following command would produce the same simulation as `./runme -s RUNDIR`:

```bash
jobrun ./runme -s -- -o OUTDIR
```

The difference here is that all options that follow the `--` are `jobrun` options. So now we don't specify the specific `RUNDIR`, but rather an encapsulating `OUTDIR` that will contain one or many `RUNDIR`'s. In the above example, no parameters are changed, so the simulation is saved in the `default` directory: `OUTDIR/default`.

If we want to change a parameter, this can be done as with the `runme` script via the `-p` option:

```bash
jobrun ./runme -s -- -o OUTDIR -p ctl.n_accel=10
```

This will produce one simulation with the parameter `control.n_accel=10`. Since we have changed a parameter for this simulation, `jobrun` treats this as an ensemble, so the output is saved in `OUTDIR/0` for simulation 0. In short, the above command is equivalent to `./runme -s -o OUTDIR -p ctl.n_accel=10`, but in the former case, the output is stored in `OUTDIR/0` and in the latter case, it is stored directly in `OUTDIR`.

The power of `jobrun` comes when we want to run an ensemble:

```bash
jobrun ./runme -s -- -o OUTDIR -p ctl.n_accel=1,5,10
```

This ensemble of simulations will appear in `OUTDIR/0`, `OUTDIR/1` and `OUTDIR/2`, respectively.

A more informative output directory can be made using the option `-a` along with `-o`:

```bash
jobrun ./runme -s -- -a -o OUTDIR -p ctl.n_accel=1,5,10
```

In this case, the run directories are `OUTDIR/ctl.nccl.1`, `OUTDIR/ctl.nccl.5` and `OUTDIR/ctl.nccl.10`, respectively.

General information about the ensemble can be found in the main ensemble directory `OUTDIR`:

- `params.txt` : contains a table of the parameter combinations set on the command line (can be used to run a new ensemble).
- `info.txt` : the same parameter table as `params.txt`, but also including an index of the `runid` (0,1,2, etc) and the `RUNDIR`:

`info.txt`:

```python
  runid    ctl.n_accel  rundir
      0              1  ctl.nccl.1
      1              5  ctl.nccl.5
      2             10  ctl.nccl.10
```

It is of course possible to define multiple parameter permutations:

```bash
jobrun ./runme -s -- -o OUTDIR -p ctl.n_accel=1,5,10 smb.alb_ice=0.3,0.4
```

To generate a more complex ensemble, using e.g. Latin-Hypercube sampling, then a two step approach is often better. First, use the `runner` command `job sample` to build the ensemble, then use `jobrun` to run it:

```bash
# Generate ensemble parameters
job sample -o lhs.txt --seed 4 -N 100 atm.c_trop_2=0.8,1.2 smb.alb_ice=0.3,0.4

# Run ensemble
jobrun ./runme -s -- -o OUTDIR -i lhs.txt
```

This two-step method facilitates checking that the ensemble was generated properly and improves reproducibility, since the exact parameter values are available in the table.

