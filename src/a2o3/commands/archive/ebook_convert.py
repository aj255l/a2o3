from importlib.resources import as_file, files
import subprocess

from pathlib import Path

from bs4 import BeautifulSoup

from a2o3.commands.archive.client import write_soup_to_path
from a2o3.commands.archive.config import ArchiveConfig, CreatorStyleConfig, Format
from a2o3.commands.archive.parse import WorkMetadata, inject_work_skin

CREATOR_STYLE_WARNING = """\033[31m
Warning: This work has a work skin.
AO3's default behavior is to strip work skins
for all download formats except HTML.\033[0m
"""
CREATOR_STYLE_PROMPT = """\033[31m
What would you like to do?
  [1]: Download anyway and strip the work skin.
  [2]: Download as HTML and preserve the work skin.
  [3]: Quit.\033[0m
"""
CREATOR_STYLE_RETRY = """\033[31m
Please enter a number from 1 to 3.\033[0m
"""

AUTO_TOC_XPATH = """\
//h:body/h:div[@id='chapters']/h:h2[@class='toc-heading']\
 | //h:body/h:div[@id='chapters']/h:div[@class='meta group']/h:h2[@class='heading']\
 | //h:body/h:div[@id='preface' or @id='afterword']/h:h2[@class='toc-heading']
"""


def should_preserve_creator_style(
    creator_style: CreatorStyleConfig, file_format: Format
) -> bool:
    """Resolve whether the current work should preserve creator styling."""
    if file_format == Format.HTML:
        return False

    if creator_style == CreatorStyleConfig.PRESERVE:
        return True

    if creator_style == CreatorStyleConfig.STRIP:
        return False

    print(CREATOR_STYLE_WARNING)
    user_input = input(CREATOR_STYLE_PROMPT)
    while not (user_input.isnumeric() and 1 <= int(user_input) <= 3):
        print(CREATOR_STYLE_RETRY)
        user_input = input(CREATOR_STYLE_PROMPT)

    user_choice = int(user_input)
    if user_choice == 1:
        return False
    if user_choice == 2:
        return True

    raise SystemExit


def get_ebook_convert_command(
    config: ArchiveConfig, meta: WorkMetadata, filename: str, xhtml_path: Path
) -> list[str]:
    """Get the `ebook-convert` command and arguments to run.

    See: https://github.com/otwcode/otwarchive/blob/45fc9ff40e4c458f25be953f35fdb811335fde9c/app/models/download_writer.rb#L67
    """
    # Build up the same options as AO3 uses
    format_specific_options = []
    match config.file_format:
        case Format.EPUB:
            format_specific_options = ["--no-default-epub-cover"]
        case Format.PDF:
            format_specific_options = [
                "--pdf-page-margin-top",
                "36",
                "--pdf-page-margin-right",
                "36",
                "--pdf-page-margin-bottom",
                "36",
                "--pdf-page-margin-left",
                "36",
                "--pdf-default-font-size",
                "17",
                "--subset-embedded-fonts",
            ]

    css_options = []
    with as_file(files("a2o3.assets").joinpath("ebooks.css")) as ebooks_css_path:
        match config.file_format:
            case Format.AZW3 | Format.EPUB | Format.MOBI:
                css_options = [
                    "--extra-css",
                    str(ebooks_css_path),
                ]

    series = []
    if meta.series is not None:
        series_title, series_part = meta.series
        series = ["--series", series_title, "--series-index", str(series_part)]

    ebook_path = config.output_path / f"{filename}.{config.file_format.value}"
    return (
        [
            "ebook-convert",
            str(xhtml_path),
            str(ebook_path),
            "--input-encoding",
            "utf-8",
            "--toc-threshold",
            "0",
            "--use-auto-toc",
            "--title",
            meta.title,
            "--title-sort",
            meta.sortable_title(),
            "--authors",
            ", ".join(meta.authors),
            "--author-sort",
            meta.sortable_authors(),
            "--comments",
            meta.summary,
            "--tags",
            ", ".join(meta.tags),
            "--pubdate",
            meta.pubdate.isoformat(),
            "--publisher",
            "Archive of Our Own",
            "--language",
            meta.language,
            "--chapter",
            AUTO_TOC_XPATH,
        ]
        + series
        + format_specific_options
        + css_options
    )


def generate_ebook_from_html(
    config: ArchiveConfig, temp_path: Path, html_path: Path, css: str
):
    """Convert HTML and CSS into an ebook using `ebook-convert`.

    This is very similar to the actual process AO3 uses to create ebooks:
      1. Extract metadata from the HTML
      1. Run `web2disk` to convert the HTML file to XHTML.
      2. Zip the resulting directory.
      3. Run `ebook-convert` to convert the XHTML to the appropriate format.

    To preserve the creator style, we inject the workskin as an external stylesheet
    before running `ebook-convert`.

    See also:
    - Ebook conversion: https://manual.calibre-ebook.com/conversion.html#id7
    - AO3 source code: https://github.com/otwcode/otwarchive/blob/45fc9ff40e4c458f25be953f35fdb811335fde9c/app/models/download_writer.rb#L43
    """
    filename = html_path.stem

    # Read the HTML into a soup
    with open(html_path, "rt") as fd:
        soup = BeautifulSoup(fd.read(), "html.parser")

    # Extract metadata about the work
    work_meta = WorkMetadata.from_soup(soup)

    # Inject this work skin into the code
    inject_work_skin(soup, css)

    # Write modified HTML back to the HTML file
    write_soup_to_path(soup, html_path)

    assets_path = temp_path / "assets"

    # Convert HTML to XHTML. This creates a directory with the following structure:
    # assets
    # ├── images/
    # │   └── ...
    # └── <filename>.xhtml
    subprocess.run(
        [
            "web2disk",
            "--base-dir",
            str(assets_path),
            "--dont-download-stylesheets",
            "--max-recursions",
            "0",
            f"file://{html_path}",
        ],
        capture_output=True,
    )

    # Convert XHTML to an ebook.
    xhtml_path = assets_path / (filename + ".xhtml")
    subprocess.run(
        get_ebook_convert_command(config, work_meta, filename, xhtml_path),
        capture_output=True,
    )
