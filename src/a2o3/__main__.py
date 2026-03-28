import argparse
import sys

from a2o3.cli.archive import register_archive_subcommand
from a2o3.commands.archive.errors import ArchiveError


def main():
    parser = argparse.ArgumentParser(prog="a2o3")
    subparsers = parser.add_subparsers(required=True)
    register_archive_subcommand(subparsers)

    args = parser.parse_args()
    try:
        args.func(args)
    except ArchiveError as exc:
        message = str(exc)
        if sys.stderr.isatty():
            message = f"\033[31m{message}\033[0m"
        raise SystemExit(message)


if __name__ == "__main__":
    main()
