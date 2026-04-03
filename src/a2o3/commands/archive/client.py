import getpass
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from yaspin import yaspin
from yaspin.spinners import Spinners

from a2o3.commands.archive.errors import AO3AuthenticationError, ArchiveError, request

LOGIN_URL = "https://archiveofourown.org/users/login"

ENV_AO3_USERNAME = "AO3_USERNAME"
ENV_AO3_PASSWORD = "AO3_PASSWORD"

CHUNK_SIZE = 128
LOGIN_TIMEOUT_SECONDS = 60


# TODO: Authenticating isn't necessary but preferred
def authenticate() -> requests.Session:
    """Authenticate to AO3, returning the session to use.

    Uses AO3_USERNAME and AO3_PASSWORD environment variables if available. Otherwise,
    prompts the user for input.
    """
    session = requests.Session()
    with yaspin(
        Spinners.bouncingBar, text="Establishing connection with AO3"
    ) as spinner:
        try:
            r = request(
                session,
                "GET",
                LOGIN_URL,
                spinner=spinner,
                timeout=LOGIN_TIMEOUT_SECONDS,
            )
        except requests.Timeout:
            spinner.write(
                "AO3 login request timed out after 60 seconds. Retrying once."
            )
            r = request(
                session,
                "GET",
                LOGIN_URL,
                spinner=spinner,
                timeout=LOGIN_TIMEOUT_SECONDS,
            )

    soup = BeautifulSoup(r.text, "html.parser")
    auth_token = soup.find("input", {"name": "authenticity_token"})

    if not auth_token or "value" not in auth_token.attrs:
        raise ArchiveError(
            "Error logging in to AO3: login page is missing authenticity_token."
        )

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
    with yaspin(Spinners.bouncingBar, text="Logging in") as spinner:
        try:
            r = request(
                session,
                "POST",
                LOGIN_URL,
                spinner=spinner,
                data=payload,
                timeout=LOGIN_TIMEOUT_SECONDS,
            )
        except requests.Timeout:
            spinner.write(
                "AO3 login request timed out after 60 seconds. Retrying once."
            )
            r = request(
                session,
                "POST",
                LOGIN_URL,
                spinner=spinner,
                data=payload,
                timeout=LOGIN_TIMEOUT_SECONDS,
            )

    if r.url.rstrip("/").endswith("/auth_error"):
        raise AO3AuthenticationError(
            "Error logging in to AO3: username or password is incorrect."
        )

    return session


def get_work_url(work_id: int) -> str:
    """Build the URL to access a single work."""
    return f"https://archiveofourown.org/works/{work_id}?style=creator"


def get_work_download_url(download_path: str) -> str:
    """Build the URL to access a single work download."""
    return f"https://download.archiveofourown.org{download_path}"


def get_user_works_url(user: str, page: int) -> str:
    """Build the URL to get all works from a user."""
    return f"https://archiveofourown.org/users/{user}/works?page={page}"


def write_response_to_path(response: requests.Response, output_path: Path):
    """Write a streamed response body to disk."""
    with open(output_path, "wb") as fd:
        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            fd.write(chunk)


def write_soup_to_path(soup: BeautifulSoup, output_path: Path):
    """Write an HTML tree to disk."""
    with open(output_path, "wt") as fd:
        fd.write(str(soup))


def create_archive_path(output: str) -> Path:
    """Create the output directory to write downloaded files to.

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

    archive_path.mkdir(parents=True)
    return archive_path
