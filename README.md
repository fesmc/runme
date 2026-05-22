# runme

`runme` performs the preliminary steps needed to run a model program — create a
run directory, copy the executable and parameter files, link input data — and
then runs it, either in the background or by submitting to a SLURM queue. It can
run a single simulation or a whole ensemble, and can generate ensembles by
factorial combination or by sampling parameter distributions.

`runme` is an installable Python package providing the `runme` command. It is
self-contained: the ensemble functionality that used to require the separate
`runner` library (via `jobrun`) is now built in.

## Install

```bash
pip install git+https://github.com/alex-robinson/runme
```

This puts the `runme` command on your path.

## How to get started

In your model directory, create a `.runme/` directory with a single file,
`info.json` (an example is provided in this repository as `.runme/info.json`),
describing the executables, the parameter files to copy, and the input folders
to link:

```json
{
    "exe_default" : "libmodel/bin/model.x",
    "par_path_as_argument" : true,
    "exe_aliases" : { "main" : "libmodel/bin/model.x" },
    "grp_aliases" : {},
    "par_paths" : { "alias" : "None" },
    "files" : ["None"],
    "dir-special" : { "None" : "target_dir_name" },
    "links" : ["input", "ice_data", "maps"]
}
```

Then create a local `.runme_config` with your per-host settings (the HPC name,
account, email, OpenMP threads, and the paths to your info and queues files):

```json
{
    "hpc"         : "dkrz_levante",
    "account"     : "ba1442",
    "jobname"     : "model",
    "omp"         : 16,
    "mem"         : -1,
    "queues_file" : ".runme/queues.json",
    "info_file"   : ".runme/info.json",
    "email"       : "",
    "mail_type"   : ["FAIL", "REQUEUE"]
}
```

That's it. The queues definition and SLURM submit templates are shipped with the
package, so you don't need to copy them into every project. `runme` resolves each
configuration file through a fallback chain:

1. the path given in `.runme_config` (your project's `.runme/`),
2. `~/.config/runme/<name>` (a user-wide override),
3. the default bundled in the package.

So a project usually carries only `.runme/info.json` and `.runme_config`. Provide
your own `.runme/queues.json` or `.runme/submit_slurm[_omp]` only when you need to
override the packaged defaults.

- Inspect available queues with `runme --list` (or `runme --list HPC`).
- Inspect the active config with `runme --config`.
- If you use a new HPC not in the packaged `queues.json`, add it (and please open
  an issue/PR so the package stays up to date).

## Running a single simulation

```bash
runme -o output/run -n par/model.nml            # stage only (create rundir, copy files)
runme -r -o output/run -n par/model.nml         # stage and run in the background
runme -s -o output/run -n par/model.nml -q short  # stage and write a SLURM submit script
runme -r -s -o output/run -n par/model.nml -q short  # stage, write submit script, and sbatch it
```

The steps carried out are:

1. create the run directory,
2. copy the executable into it,
3. copy the relevant parameter files,
4. link the input-data folders,
5. run in the background or submit to the queue (or, with neither `-r` nor `-s`,
   just stage everything).

Parameters can be modified inline with `-p KEY=VALUE [KEY=VALUE ...]`; the changes
are written to the parameter file copied into the run directory. Each run
directory also gets a `runme.json` record and `params.txt` / `info.txt` tables
describing the run.

## Ensembles

Any `-p` value that is a comma list, a range, or a distribution turns the run into
an ensemble. The output directory `-o OUTDIR` then holds one run directory per
ensemble member:

```bash
runme -r -o OUTDIR -n par/model.nml -p ctl.n_accel=1,5,10
```

This runs three simulations in `OUTDIR/0`, `OUTDIR/1`, `OUTDIR/2`. Single-valued
`-p` entries given alongside ensemble dimensions are *fixed overrides* applied to
every member:

```bash
runme -r -o OUTDIR -n par/model.nml -p ctl.n_accel=1,5,10 ctl.year=5000 smb.alb_ice=0.3,0.4
```

Use `-a` for run directories named from the parameter values instead of the run id:

```bash
runme -r -a -o OUTDIR -n par/model.nml -p ctl.n_accel=1,5,10
```

### Ensemble output files

In `OUTDIR`:

- `params.txt` / `info.txt` — the full parameter table (ensemble dimensions *and*
  fixed overrides); `info.txt` adds the `runid` and `rundir` columns.
- `params_ensemble.txt` / `info_ensemble.txt` — only the permuted ensemble
  dimensions.

```
  runid  ctl.n_accel  rundir
      0            1   0
      1            5   1
      2           10   2
```

Each member run directory additionally gets its own single-row `params.txt` /
`info.txt` and a `runme.json` record, so any run directory — single or ensemble
member — loads the same way.

### Selecting a subset of members

Run only some members with `-j` (slurm `--array` syntax):

```bash
runme -r -o OUTDIR -n par/model.nml -p ctl.n_accel=1,5,10 -j 0,2     # members 0 and 2
runme -r -o OUTDIR -n par/model.nml -i lhs.txt -j 0-9               # first ten members
```

### Generating ensembles

For complex ensembles, a two-step approach is often clearer: generate the
parameter set first (so you can check it and keep it for reproducibility), then
run it with `-i`.

Factorial combination:

```bash
runme product ctl.n_accel=1,5,10 smb.alb_ice=0.3,0.4 -o grid.txt
runme -r -o OUTDIR -n par/model.nml -i grid.txt
```

Latin-hypercube (or Monte-Carlo) sampling of distributions:

```bash
runme sample atm.c_trop=U?0.8,1.2 smb.alb_ice=N?0.35,0.05 -N 100 --seed 4 -o lhs.txt
runme -r -o OUTDIR -n par/model.nml -i lhs.txt
```

Distribution specs: `U?MIN,MAX` (uniform), `N?MEAN,SD` (normal), or any
`scipy.stats` distribution as `TYPE?[SHP,]LOC,SCALE`. Discrete values (`a=1,2,3`)
and ranges (`a=0:10:5`) are also accepted.

### Dry run

Add `--dry-run` to print what would be staged and run for each member without
creating or running anything.
