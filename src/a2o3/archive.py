import getpass
import itertools
import os
import sys
import threading
from typing import TypeAlias, Callable, Any

import requests
from bs4 import BeautifulSoup
from yaspin import yaspin
from yaspin.spinners import Spinners

from argparse import Namespace

Thunk: TypeAlias = Callable[[], Any]


LOGIN_URL = "https://archiveofourown.org/users/login"

ENV_AO3_USERNAME = "AO3_USERNAME"
ENV_AO3_PASSWORD = "AO3_PASSWORD"


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


def get_user_work_url(user: str) -> str:
    """Builds the URL to get all works from a user."""
    return f"https://archiveofourown.org/users/{user}/works"


def archive(args: Namespace) -> None:
    """
    Downloads EPUBs from AO3 and writes them to the specified output directory.

    Requires authentication to AO3.
    """
    session = authenticate()

    # Request all works from a user.
    with yaspin(
        Spinners.bouncingBar, text=f"Querying {args.author}'s works"
    ) as spinner:
        r = session.get(get_user_work_url(args.author))
        r.raise_for_status()
        spinner.ok("done")

    print(r.text)

    print(args)
