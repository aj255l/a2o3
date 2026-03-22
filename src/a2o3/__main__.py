import argparse

from a2o3.archive import archive


def main():
    parser = argparse.ArgumentParser(prog="a2o3")
    subparsers = parser.add_subparsers(required=True)

    # `a2o3 archive`: Scrape and download works from AO3.
    archive_parser = subparsers.add_parser(
        "archive", help="Scrape and download works from AO3."
    )
    archive_group = archive_parser.add_mutually_exclusive_group()
    archive_group.add_argument(
        "--user",
        help="User to scrape the works of. This must be the author's username, not a pseudonym.",
    )
    archive_group.add_argument(
        "--work",
        type=int,
        help="Work ID to scrape.",
    )
    archive_parser.add_argument(
        "--output",
        default=".",
        help="Path to output directory. If the directory already exists, files will be written to OUTPUT/archive.",
    )
    archive_parser.set_defaults(func=archive)

    args = parser.parse_args()
    args.func(args)
