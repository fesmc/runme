# runme project layout

This README documents the files runme reads in a project. Most projects do
not need to touch every file: the packaged defaults are good out of the box,
and `runme config init` only scaffolds what is genuinely project-local.

Run `runme info` to see exactly which file each path currently resolves to.

## Config

`.runme/config.toml` is the active per-host config: cluster, SLURM account,
email, OpenMP threads, job name, memory default, notification types. It is
gitignored so each contributor keeps their own.

`.runme/config.default.toml` is the tracked template. `runme config init`
copies it to `config.toml` on first use; runme itself never reads the
default. Edit `config.default.toml` to change what new contributors get on
their first init; edit `config.toml` to change *your* settings.

## Queues

HPC queue aliases for runme. Each top-level key in `queues.json` is a
cluster name. Set `hpc` in `.runme/config.toml` to one of these.

Inspect the table with `runme queues` (current cluster) or `runme queues
--all`. For a new cluster, run `runme check queues` on the login node to
discover usable (partition, qos, wall) triplets and merge them in.

`queues.json` resolves through a fallback chain: project ->
`~/.config/runme/` -> packaged default. Most projects can rely on the
packaged version; run `runme config queues` only when you need a local
copy to customise.

`job_template` (per cluster) is a path to the SLURM submit-script template.
It resolves through the same fallback chain.

## Info

`.runme/info.json` describes the model itself: executables, parameter file
paths, exe and group aliases, file/link rules used by `runme stage`. It is
project-local with no fallback chain because nothing about it is shared
across projects.

Edit it whenever you add a new executable target or change how parameter
files are organised.

## Submit templates

`submit_slurm` and `submit_slurm_omp` are the SLURM job-script templates.
`<PLACEHOLDER>` tokens are filled at submit time with the resolved queue,
account, executable command, OpenMP block, and so on.

These resolve through the same project / `~/.config/runme/` / packaged
fallback chain as `queues.json`. Override only when your cluster needs a
nonstandard submit recipe.
