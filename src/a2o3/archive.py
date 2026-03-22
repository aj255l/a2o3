import getpass
import os
import re
from pathlib import Path
from urllib.parse import unquote
from argparse import Namespace

import requests
from bs4 import BeautifulSoup
from yaspin import yaspin
from yaspin.spinners import Spinners


LOGIN_URL = "https://archiveofourown.org/users/login"

ENV_AO3_USERNAME = "AO3_USERNAME"
ENV_AO3_PASSWORD = "AO3_PASSWORD"

CHUNK_SIZE = 128


def authenticate() -> requests.Session:
    """
    Authenticates to AO3, returning the session to use.

    Uses AO3_USERNAME and AO3_PASSWORD environment variables if available.
    Otherwise, prompts the user for input.
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
    return f"https://archiveofourown.org/works/{work_id}"


def get_work_download_url(download_path: str) -> str:
    """Builds the URL to access a single work."""
    return f"https://download.archiveofourown.org{download_path}"


def get_user_works_url(user: str, page: int) -> str:
    """Builds the URL to get all works from a user."""
    return f"https://archiveofourown.org/users/{user}/works?page={page}"


def get_download_path(soup: BeautifulSoup) -> str:
    """
    Gets the path for downloading a work as an EPUB.

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
    epub_path = download_options[1].a.get("href")

    return epub_path


def check_headers_for_attachment(response: requests.Response) -> str:
    """
    Asserts that the content of the provided response is an attachment. Returns the filename as a UTF-8 encoded string.
    """
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment")

    charset, encoded_filename = re.search(
        r"filename\*\s*=\s*([^']+)''(.+)", content_disposition
    ).groups()

    # TODO(anna): Fall back on filename if decoding error
    return unquote(encoded_filename, encoding=charset)


def archive_work(session: requests.Session, work_id: int, output: Path):
    """
    Downloads `work_id` as an EPUB from AO3 and writes to the specified output directory.
    """
    with yaspin(Spinners.bouncingBar, text=f"Downloading work id {work_id}") as spinner:
        r = session.get(get_work_url(work_id))
        r.raise_for_status()
        work_soup = BeautifulSoup(r.text, "html.parser")

        download_path = get_download_path(work_soup)
        r = session.get(get_work_download_url(download_path))
        r.raise_for_status()
        filename = check_headers_for_attachment(r)

        with open(output / filename, "wb") as fd:
            for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                fd.write(chunk)

        spinner.ok("✔")


def get_user_page_count(soup: BeautifulSoup) -> int:
    """
    Gets the number of pages in the user works navigation bar.

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
    """
    Gets the ids of all the works listed in a user's page.

    Work blurbs are identified by the role `article`:
    ```html
    <!--main content-->
    <h3 class="landmark heading">
     Listing Works
    </h3>
    <ol class="work index group">
     <li class="work blurb group work-<work_id> user-<user_id>" id="work_<work_id>" role="article">
     ...
     </li>
     <li class="work blurb group work-<work_id> user-<user_id>" id="work_<work_id>" role="article">
     </li>
    </ol>
    ```
    """
    work_blurbs = soup.find_all("li", {"role": "article"})
    work_ids = []

    for work_blurb in work_blurbs:
        work_id = re.match(r"work_([0-9]+)", work_blurb["id"]).group(1)
        work_ids.append(int(work_id))

    return work_ids


def archive_user(session: requests.Session, user: str, output: Path):
    """
    Downloads all works from a user as EPUBs and writes them to the specified output directory.
    """
    page = 1
    with yaspin(Spinners.bouncingBar, text=f"Querying works from {user}"):
        works_url = get_user_works_url(user, page)
        r = session.get(works_url)
        r.raise_for_status()

    works_soup = BeautifulSoup(r.text, "html.parser")
    page_count = get_user_page_count(works_soup)
    for work_id in get_page_work_ids(works_soup):
        archive_work(session, work_id, output)

    while page < page_count:
        page += 1
        works_url = get_user_works_url(user, page)

        r = session.get(works_url)
        r.raise_for_status()

        works_soup = BeautifulSoup(r.text, "html.parser")
        for work_id in get_page_work_ids(works_soup):
            archive_work(session, work_id, output)


def archive(args: Namespace):
    """
    Downloads EPUBs from AO3 and writes them to the specified output directory.

    Requires authentication to AO3.
    """
    output = Path(args.output)
    if output.exists():
        # Create the `archive` directory at the output path.
        # If `archive` already exists, give it a unique filename.
        output = Path(args.output) / "archive"
        if output.exists():
            counter = 1
            candidate = output
            while candidate.exists():
                candidate = output.with_name(f"{output.name}_{counter}")
                counter += 1

            output = candidate
            print(
                f"{args.output}/archive already exists. Writing to {args.output}/{output.name} instead."
            )

    output.mkdir(parents=True, exist_ok=False)

    session = authenticate()

    if args.work is not None:
        archive_work(session, args.work, output)

    elif args.user is not None:
        archive_user(session, args.user, output)
