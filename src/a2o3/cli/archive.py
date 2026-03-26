from a2o3.commands.archive.command import archive
from a2o3.commands.archive.config import Format, str_to_format


def register_archive_subcommand(subparsers):
    """Register the `archive` subcommand."""
    archive_parser = subparsers.add_parser(
        "archive", help="Scrape and download works from AO3."
    )
    archive_selector_group = archive_parser.add_mutually_exclusive_group()
    archive_selector_group.add_argument(
        "--user",
        "-u",
        help=(
            "User to scrape the works of. "
            "This must be the author's username, not a pseudonym."
        ),
    )
    archive_selector_group.add_argument(
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
        type=str_to_format,
        default=Format.HTML,
        help="Format to download files as: AZW3, EPUB, MOBI, PDF, or HTML (default).",
    )
    archive_style_group = archive_parser.add_mutually_exclusive_group()
    archive_style_group.add_argument(
        "--preserve-creator-style",
        action="store_true",
        default=False,
        help=(
            "Automatically apply work skins to downloaded works. "
            "Works will be downloaded as HTML and converted to alternative formats. "
        ),
    )
    archive_style_group.add_argument(
        "--strip-creator-style",
        action="store_true",
        default=False,
        help=(
            "Disable the confirmation prompt for works with work skins. "
            "Works will be downloaded using AO3's ebook conversion process."
        ),
    )
    archive_parser.set_defaults(func=archive)
