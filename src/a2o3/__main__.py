import argparse

from a2o3.cli.archive import register_archive_subcommand


def main():
    parser = argparse.ArgumentParser(prog="a2o3")
    subparsers = parser.add_subparsers(required=True)
    register_archive_subcommand(subparsers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
