import argparse

from a2o3.archive import archive, Format


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
        "-u",
        help=(
            "User to scrape the works of. "
            "This must be the author's username, not a pseudonym."
        ),
    )
    archive_group.add_argument(
        "--work",
        "-w",
        type=int,
        help="Work ID to scrape.",
    )
    archive_parser.add_argument(
        "--output",
        "-o",
        default=".",
        help=(
            "Path to output directory. "
            "If the directory already exists, files will be written to OUTPUT/archive."
        ),
    )
    archive_parser.add_argument(
        "--format",
        "-f",
        type=Format,
        default=Format.HTML,
        help="Format to download files as: AZW3, EPUB, MOBI, PDF, or HTML (default).",
    )
    archive_parser.set_defaults(func=archive)

    args = parser.parse_args()
    args.func(args)
