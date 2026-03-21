import argparse

from a2o3.archive import archive


def main():
    parser = argparse.ArgumentParser(prog="a2o3")
    subparsers = parser.add_subparsers(required=True)

    # `a2o3 archive`: Scrape and download works from AO3.
    archive_parser = subparsers.add_parser(
        "archive", help="Scrape and download works from AO3."
    )
    archive_parser.add_argument(
        "--author",
        required=True,
        help="Author to scrape the works of. This must be the author's username, not a pseudonym.",
    )
    archive_parser.add_argument(
        "--output",
        default=".",
        help="Path to output directory. Files will be written to OUTPUT/archive",
    )
    archive_parser.set_defaults(func=archive)

    args = parser.parse_args()
    args.func(args)
