# runme

`runme` performs the preliminary steps needed to run a model program — create a
run directory, copy the executable and parameter files, link input data — and
then runs it, either in the background or by submitting to a SLURM queue. It can
run a single simulation or a whole ensemble, and can generate ensembles by
factorial combination or by sampling parameter distributions.

`runme` is an installable Python package providing the `runme` command. It is
self-contained: the ensemble functionality that used to require the separate
`runner` library (via `jobrun`) is now built in.

## Acknowledgments

`runme` builds on the [`runner`](https://github.com/perrette/runner) package by
Mahé Perrette, a flexible framework for sampling parameters and for running and
analyzing model ensembles. `runme` reimplements a focused subset of that
functionality — factorial combination, Latin-hypercube and Monte-Carlo sampling,
and ensemble execution — while stripping away the more complex methods (Bayesian
analysis, iterative importance sampling, weighted resampling). Here the ensemble
"run" step is handled simply by calling `runme` itself, rather than by wrapping a
separate per-simulation script.

If you need those more advanced methods, use the original
[`perrette/runner`](https://github.com/perrette/runner) package directly.

## Install

```bash
pip install git+https://github.com/fesmc/runme
```

This puts the `runme` command on your path. To upgrade later, add `--upgrade` (or
`--force-reinstall`) to the same command. The only dependencies are `numpy` and
`scipy` (used by the ensemble sampling), installed automatically.

Once installed, `runme --init` scaffolds a project (see below), `runme --config`
manages your local settings, and `runme --list` shows the available HPC queues.

## How to get started

The quickest way is `runme --init` in your model directory. It creates a
`.runme/` directory with templates to edit:

```bash
cd $MODEL_PATH
runme --init        # creates .runme/{info.json, runme_config, queues.json}
# edit .runme/info.json for your model; set hpc/account in .runme/runme_config
runme --config      # creates your local .runme_config from the template
```

Run `runme --init` again at any time to validate the configuration: it reports
missing files or keys, flags unset placeholders, checks that your `hpc` exists in
the queues file, and fills in any genuinely-missing template files (without
overwriting existing ones).

The rest of this section explains the files `--init` scaffolds.

### info.json

`.runme/info.json` describes the executables, the parameter files to copy, and
the input folders to link. It is the one genuinely project-specific file:

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
  an issue/PR so the package stays up to date). On the new cluster's login node,
  `runme check queues [NAME]` introspects SLURM (via `scontrol`/`sacctmgr`),
  prints a ready-made block of the `(partition, qos, wall)` triplets you can
  actually submit to, and offers to merge it into your queues file. Aliases are
  guessed from whichever of partition/qos varies, falling back to
  `queue1, queue2, ...` (rename them afterwards) when both vary.

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
are written to the parameter file copied into the run directory. A `-p` key must
already exist in one of the parameter files being staged — runme will not create
new parameters, so a typo'd name is reported rather than silently added.

### How `-n` is used

For projects whose executable takes the parameter file as an argument
(`par_path_as_argument=true`), `-n` names that file: it is copied into the run
directory and passed to the model.

For projects that read their own fixed-name parameter files
(`par_path_as_argument=false`, e.g. climber-x), `-n` is **optional** and acts as
an *overlay*: the parameters in the named file are merged into the project's
default parameter files. Precedence is

```
default parameter files  →  -n overlay  →  -p overrides
```

so a `-p` flag wins over the same parameter set in the overlay file.

## Cases

A *case* is just a normal (partial or complete) namelist parameter file kept in
a `cases/` folder, capturing a configuration worth reusing. Use one via `-n`:
pass its path, or pass a bare name and runme looks it up under `cases/`
(`cases/NAME`, or `cases/NAME.*` when a single file matches, so the extension can
be omitted):

```bash
runme -r -o output/run -n spinup                 # uses cases/spinup(.nml)
runme -r -o output/run -n spinup -p ctl.year=10  # case, then tweak on top
```

Because a case is loaded through the overlay path above, `-p` overrides layer on
top of it — handy for running permutations from a saved baseline.

Save the parameters applied in any run directory as a case with:

```bash
runme case save NAME -o RUNDIR
```

This reads `RUNDIR/runme.json` and writes its applied parameters as a partial
namelist to `cases/NAME.nml`. It works for an ensemble member directory too.

### What gets produced

Every run directory — for a single simulation or for each ensemble member — is
self-describing and contains:

- the executable, the (parameter-edited) parameter files, and the input-data links;
- `runme.json` — a machine-readable record of the run: the full `runme` command,
  the model command line, the applied parameters, the git revision, and a status
  (`staged` / `prepared` / `running` / `submitted`);
- `params.txt` — a one-row table of the parameter names and values for this run;
- `info.txt` — the same row prefixed with the `runid` and suffixed with the
  `rundir`, so a directory can be located and loaded uniformly.

Because single simulations and ensemble members write the same files, downstream
tooling can load any run directory the same way.

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
