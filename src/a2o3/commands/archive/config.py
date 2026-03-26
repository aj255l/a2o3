from argparse import ArgumentTypeError, Namespace
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from a2o3.commands.archive.client import create_archive_path


class Format(Enum):
    """Supported file formats for download from AO3."""

    AZW3 = "azw3"
    EPUB = "epub"
    MOBI = "mobi"
    PDF = "pdf"
    HTML = "html"


def str_to_format(s: str) -> Format:
    """Convert a case-insensitive string to a Format or raise an error."""
    try:
        return Format(s.lower())
    except ValueError as exc:
        raise ArgumentTypeError(
            f"Invalid format: {s}. Must be one of {[f.value for f in Format]}"
        ) from exc


class CreatorStyleConfig(Enum):
    """Configuration for handling works with work skins.

    Members:
        WARN: Warn the user about lossy formats and require confirmation.
        PRESERVE: Automatically preserve creator styles.
        STRIP: Automatically strip creator styles. This is the default AO3 behavior.
    """

    WARN = "warn"
    PRESERVE = "preserve"
    STRIP = "strip"


@dataclass
class ArchiveConfig:
    """Configuration for the `archive` subcommand.

    Attributes:
        file_format: Output file format for archived works.
        output_path: Path to write archived works to.
        creator_style: Configuration for handling creator style.
    """

    file_format: Format
    output_path: Path
    creator_style: CreatorStyleConfig

    def __init__(self, args: Namespace):
        self.file_format = args.format
        self.output_path = create_archive_path(args.output)
        if args.preserve_creator_style:
            self.creator_style = CreatorStyleConfig.PRESERVE
        elif args.strip_creator_style:
            self.creator_style = CreatorStyleConfig.STRIP
        else:
            self.creator_style = CreatorStyleConfig.WARN
