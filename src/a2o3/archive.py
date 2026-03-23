import getpass
import os
import re

from dataclasses import dataclass
from enum import Enum
from argparse import Namespace, ArgumentTypeError
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from yaspin import yaspin
from yaspin.spinners import Spinners

LOGIN_URL = "https://archiveofourown.org/users/login"

ENV_AO3_USERNAME = "AO3_USERNAME"
ENV_AO3_PASSWORD = "AO3_PASSWORD"

CHUNK_SIZE = 128

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


class Format(Enum):
    """Supported file formats for download from AO3."""

    AZW3 = "azw3"
    EPUB = "epub"
    MOBI = "mobi"
    PDF = "pdf"
    HTML = "html"


def str_to_format(s: str) -> Format:
    """Converts a case-insensitive string to a Format or raises an error."""
    try:
        return Format(s.lower())
    except ValueError:
        raise ArgumentTypeError(
            f"Invalid format: {s}. Must be one of {[f.value for f in Format]}"
        )


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


def authenticate() -> requests.Session:
    """Authenticates to AO3, returning the session to use.

    Uses AO3_USERNAME and AO3_PASSWORD environment variables if available. Otherwise,
    prompts the user for input.
    """
    session = requests.Session()
    with yaspin(Spinners.bouncingBar, text="Establishing connection with AO3"):
        r = session.get(LOGIN_URL)
        r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    auth_token = soup.find("input", {"name": "authenticity_token"})

    if not auth_token or "value" not in auth_token.attrs:
        raise RuntimeError("Could not find authenticity_token")

    # Check for the presence of AO3_USERNAME and AO3_PASSWORD environment variables.
    # Otherwise, prompt the user for a username and password.
    username = os.environ.get(ENV_AO3_USERNAME) or input("username: ")
    password = os.environ.get(ENV_AO3_PASSWORD) or getpass.getpass(prompt="password: ")

    # Build the POST request for login.
    payload = {
        "authenticity_token": auth_token.attrs["value"],
        "user[login]": username,
        "user[password]": password,
        "commit": "Log in",
    }
    with yaspin(Spinners.bouncingBar, text="Logging in"):
        r = session.post(LOGIN_URL, data=payload)
        r.raise_for_status()

    return session


def get_work_url(work_id: int) -> str:
    """Builds the URL to access a single work."""
    return f"https://archiveofourown.org/works/{work_id}?style=creator"


def get_work_download_url(download_path: str) -> str:
    """Builds the URL to access a single work."""
    return f"https://download.archiveofourown.org{download_path}"


def get_user_works_url(user: str, page: int) -> str:
    """Builds the URL to get all works from a user."""
    return f"https://archiveofourown.org/users/{user}/works?page={page}"


def has_creator_style(soup: BeautifulSoup) -> bool:
    """Determines whether a creator style is applied.

    The relevant location in the HTML is under the `work navigation actions` class:
    ```html
    <ul class="work navigation actions">
     ...
     <li class = "style"> </li>
     ...
    </ul>
    ```
    """
    work_nav_class = soup.find("ul", class_="work navigation actions")
    print(work_nav_class)
    return work_nav_class.find("li", class_="style") is not None


def get_download_path(soup: BeautifulSoup, file_format: Format) -> str:
    """Gets the path for downloading a work as the specified format.

    The relevant location in the HTML is under the `download` class:
    ```html
    <li class="download">
     <noscript> <h4 class="heading"> Download </h4> </noscript>
     <button class="hidden"> Download </button>
     <ul class="expandable secondary">
      <li> <a href="..."> AZW3 </a> </li>
      <li> <a href="..."> EPUB </a> </li>
      <li> <a href="..."> MOBI </a> </li>
      <li> <a href="..."> PDF </a> </li>
      <li> <a href="..."> HTML </a> </li>
     </ul>
    </li>
    ```
    """
    download_class = soup.find("li", class_="download")
    download_options = download_class.find_all("li")
    match file_format:
        case Format.AZW3:
            download_path = download_options[0].a.get("href")
        case Format.EPUB:
            download_path = download_options[1].a.get("href")
        case Format.MOBI:
            download_path = download_options[2].a.get("href")
        case Format.PDF:
            download_path = download_options[3].a.get("href")
        case Format.HTML:
            download_path = download_options[4].a.get("href")

    return str(download_path)


def check_headers_for_attachment(response: requests.Response) -> str:
    """Asserts that the content of the provided response is an attachment.

    Returns the filename as a UTF-8 encoded string.
    """
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment")

    charset, encoded_filename = re.search(
        r"filename\*\s*=\s*([^']+)''(.+)", content_disposition
    ).groups()

    # TODO(anna): Fall back on filename if decoding error
    return unquote(encoded_filename, encoding=charset)


def archive_work(session: requests.Session, config: ArchiveConfig, work_id: int):
    """Downloads `work_id` as from AO3 and writes to the specified output directory."""
    with yaspin(Spinners.bouncingBar, text=f"Downloading work id {work_id}") as spinner:
        r = session.get(get_work_url(work_id))
        r.raise_for_status()
        work_soup = BeautifulSoup(r.text, "html.parser")

        preserve_style = False
        if has_creator_style(work_soup) and config.file_format != Format.HTML:
            if config.creator_style == CreatorStyleConfig.WARN:
                spinner.stop()

                def is_valid(s: str) -> bool:
                    return s.isnumeric() and (1 <= int(s) <= 3)

                print(CREATOR_STYLE_WARNING)
                user_input = input(CREATOR_STYLE_PROMPT)
                while not is_valid(user_input):
                    print(CREATOR_STYLE_RETRY)
                    user_input = input(CREATOR_STYLE_PROMPT)

                if user_input == 1:
                    preserve_style = False
                elif user_input == 2:
                    preserve_style = True
                else:
                    raise SystemExit

                spinner.start()
            elif config.creator_style == CreatorStyleConfig.PRESERVE:
                preserve_style = True

        if preserve_style:
            # This flag should only be set if the user chose a lossy format.
            assert config.file_format != Format.HTML

            raise NotImplementedError
        else:
            download_path = get_download_path(work_soup, config.file_format)
            r = session.get(get_work_download_url(download_path))
            r.raise_for_status()
            filename = check_headers_for_attachment(r)

            with open(config.output_path / filename, "wb") as fd:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    fd.write(chunk)

        spinner.ok("✔")


def get_user_page_count(soup: BeautifulSoup) -> int:
    """Gets the number of pages in the user works navigation bar.

    The relevant location in the HTML is under the `pagination actions pagy` class:
    ```html
    <ol aria-label="Pagination" class="pagination actions pagy" role="navigation">
     <li class="previous">
      <span class="disabled"> ← Previous </span>
     </li>
     <li>
      <a aria-current="page" aria-disabled="true" class="current" role="link"> 1 </a>
     </li>
     [...]
     <li>
      <a href="..."> <page_count> </a>
     </li>
     <li class="next">
      <a href="..."> Next → </a>
     </li>
    </ol>
    ```
    """
    pagy_class = soup.find("li", class_="pagination actions pagy")

    # If a user has <20 works, there aren't any pages to navigate.
    if pagy_class is None:
        return 1

    # Otherwise, the last page is the second-to-last element in the list.
    pagy_last_page = pagy_class.find_all("li")[-2]
    page_count = pagy_last_page.a.string

    return int(page_count.strip())


def get_page_work_ids(soup: BeautifulSoup) -> list[int]:
    """Gets the ids of all the works listed in a user's page.

    Work blurbs are identified by the role `article`:
    ```html
    <!--main content-->
    <h3 class="landmark heading">
     Listing Works
    </h3>
    <ol class="work index group">
     <li class="..." id="work_<work_id>" role="article">
     ...
     </li>
     <li class="..." id="work_<work_id>" role="article">
     </li>
    </ol>
    ```
    """
    work_blurbs = soup.find_all("li", {"role": "article"})
    work_ids = []

    for work_blurb in work_blurbs:
        work_id = str(work_blurb["id"])
        work_id = re.match(r"work_([0-9]+)", work_id).group(1)
        work_ids.append(int(work_id))

    return work_ids


def archive_user(session: requests.Session, config: ArchiveConfig, user: str):
    """Downloads all works from a user as EPUBs and writes them to the specified output
    directory."""
    page = 1
    with yaspin(Spinners.bouncingBar, text=f"Querying works from {user}"):
        works_url = get_user_works_url(user, page)
        r = session.get(works_url)
        r.raise_for_status()

    works_soup = BeautifulSoup(r.text, "html.parser")
    page_count = get_user_page_count(works_soup)
    for work_id in get_page_work_ids(works_soup):
        archive_work(session, config, work_id)

    while page < page_count:
        page += 1
        works_url = get_user_works_url(user, page)

        r = session.get(works_url)
        r.raise_for_status()

        works_soup = BeautifulSoup(r.text, "html.parser")
        for work_id in get_page_work_ids(works_soup):
            archive_work(session, config, work_id)


def create_archive_path(output: str) -> Path:
    """Creates the output directory to write downloaded files to.

    If the directory already exists, creates an `archive` directory as a subfolder.
    """
    archive_path = Path(output)
    if archive_path.exists():
        # Create the `archive` directory at the output path.
        # If `archive` already exists, give it a unique filename.
        archive_path = Path(output) / "archive"
        if archive_path.exists():
            counter = 1
            candidate = archive_path
            while candidate.exists():
                candidate = archive_path.with_name(f"{archive_path.name}_{counter}")
                counter += 1

            archive_path = candidate
            print(
                f"{output}/archive already exists. "
                f"Writing to {output}/{archive_path.name} instead."
            )

    archive_path.mkdir(parents=True, exist_ok=False)
    return archive_path


def archive(args: Namespace):
    """Downloads works from AO3 and writes them to the specified output directory.

    Requires authentication to AO3.
    """
    config = ArchiveConfig(args)

    session = authenticate()

    if args.work is not None:
        archive_work(session, config, args.work)

    elif args.user is not None:
        archive_user(session, config, args.user)
