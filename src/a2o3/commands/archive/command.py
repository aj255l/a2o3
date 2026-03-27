import shutil
from argparse import Namespace

import requests
from bs4 import BeautifulSoup
from yaspin import yaspin
from yaspin.spinners import Spinners

from a2o3.commands.archive.client import (
    authenticate,
    get_user_works_url,
    get_work_download_url,
    get_work_url,
    write_response_to_path,
)
from a2o3.commands.archive.config import ArchiveConfig, Format
from a2o3.commands.archive.parse import (
    check_headers_for_attachment,
    get_download_path,
    get_page_work_ids,
    get_user_page_count,
    get_work_skin,
    has_creator_style,
)
from a2o3.commands.archive.ebook_convert import (
    generate_ebook_from_html,
    should_preserve_creator_style,
)


def archive_work(session: requests.Session, config: ArchiveConfig, work_id: int):
    """Download `work_id` as from AO3 and write to the specified output directory."""
    with yaspin(Spinners.bouncingBar, text=f"Downloading work id {work_id}") as spinner:
        r = session.get(get_work_url(work_id))
        r.raise_for_status()
        work_soup = BeautifulSoup(r.text, "html.parser")

        preserve_style = False
        if has_creator_style(work_soup) and config.file_format != Format.HTML:
            spinner.stop()
            preserve_style = should_preserve_creator_style(
                config.creator_style, config.file_format
            )
            spinner.start()

        if preserve_style:
            # This flag should only be set if the user chose a lossy format.
            assert config.file_format != Format.HTML

            # If we care about preserving style, we need to:
            #   - Download as HTML and request the stylesheet.
            #   - Convert the HTML into an ebook ourselves.
            html_download_path = get_download_path(work_soup, Format.HTML)
            r = session.get(get_work_download_url(html_download_path))
            r.raise_for_status()
            filename = check_headers_for_attachment(r)

            # Write HTML to a temporary directory
            # TODO(anna): Make this do less directory creation and removal.
            temp_path = config.output_path / "tmp"
            temp_path.mkdir()
            temp_html = temp_path / filename
            write_response_to_path(r, temp_html)

            css = get_work_skin(work_soup)

            # Transform HTML into ebook
            generate_ebook_from_html(config, temp_path, temp_html, css)

            # Clean up tmp directory
            shutil.rmtree(temp_path)

        else:
            # If we don't care about preserving style, we can directly request
            # a download and write to the output directory.
            download_path = get_download_path(work_soup, config.file_format)
            r = session.get(get_work_download_url(download_path))
            r.raise_for_status()
            filename = check_headers_for_attachment(r)
            write_response_to_path(r, config.output_path / filename)

        spinner.ok("✔")


def archive_user(session: requests.Session, config: ArchiveConfig, user: str):
    """Download all works from a user as EPUBs and write them to the specified output
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


def archive(args: Namespace):
    """Download works from AO3 and write them to the specified output directory.

    Requires authentication to AO3.
    """
    config = ArchiveConfig(args)
    session = authenticate()

    if args.work is not None:
        archive_work(session, config, args.work)
    elif args.works is not None:
        for work_id in args.works:
            archive_work(session, config, work_id)
    elif args.user is not None:
        archive_user(session, config, args.user)
