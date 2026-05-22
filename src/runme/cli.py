"""Command-line entrypoint for runme.

Phase 1 provides only the argument-parser skeleton so the installed ``runme``
console script resolves and ``runme --help`` / ``runme --version`` work. The
single-simulation flow is moved here in Phase 2, and ensemble dispatch is added
in Phase 4.
"""
import argparse

from runme import __version__


def build_parser():
    """Construct the top-level argument parser.

    Subcommands and the full option set are added in later phases. For now this
    only wires up ``--version`` so the entrypoint is verifiably installed.
    """
    parser = argparse.ArgumentParser(
        prog="runme",
        description="Stage, run, and submit single simulations and ensembles.",
    )
    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s " + __version__
    )
    return parser


def main(argv=None):
    parser = build_parser()
    parser.parse_args(argv)
    # Phase 1 placeholder: no behavior wired up yet.
    parser.print_help()


if __name__ == "__main__":
    main()
