import re
from datetime import date
from urllib.parse import unquote

import langcodes
import requests
from bs4 import BeautifulSoup

from a2o3.commands.archive.config import Format


# TODO: Add a helper for propagating parse errors cleanly.
WORKSKIN_TAG = "workskin"
AUTHOR_PSEUD_REGEX = r"\s*\([^)]*\)$"
SORTED_AUTHOR_REGEX = r'^[\+\-=_\?!\'"\./]'


class WorkMetadata:
    """Metadata fields for AO3 works.

    Attributes:
        title: Title of the work
        authors: Author(s) of the work
        tags: Tags associated with the book
        pubdate: Date of publication
        summary: Summary of the work
        language: Work language
        series: Series title and position of the work, or None
    """

    title: str
    authors: list[str]
    tags: list[str]
    pubdate: date
    summary: str
    language: str
    series: tuple[str, int] | None

    def __init__(
        self,
        title: str,
        authors: list[str],
        tags: list[str],
        pubdate: date,
        summary: str,
        language: str,
        series: tuple[str, int] | None,
    ):
        self.title = title
        self.authors = authors
        self.tags = tags
        self.pubdate = pubdate
        self.summary = summary
        self.language = language
        self.series = series

    @classmethod
    def from_soup(cls, soup: BeautifulSoup) -> "WorkMetadata":
        """Create work metadata from the downloaded work HTML soup.

        This takes in the HTML soup of the work when downloaded as HTML, _not_ the soup
        of the work's web page.

        The relevant HTML is located in the stats section:
        ```html
        <div class="meta">
         <dl class="tags">
          <dt>Rating:</dt>
           <dd><a href="...">[Rating]</a></dd>
          <dt>Archive Warnings:</dt>
           <dd><a href="...">[Warning]</a>, [...]</dd>
          <dt>Category:</dt>
           <dd><a href="">[Category]</a></dd>
          <dt>Fandom:</dt>
           <dd><a href="...">[Fandom]</a></dd>
          <dt>Relationships:</dt>
           <dd><a href="...">[Relationship]</a>, [...]</dd>
          <dt>Characters:</dt>
           <dd><a href="...">[Character]</a>, [...]</dd>
          <dt>Additional Tags:</dt>
           <dd><a href="...">[Additional Tag]</a>, [...]</dd>
          <dt>Language:</dt>
           <dd>[Language]</dd>
          <dt>Series:</dt>
           <dd>Part [Series Number] of <a href="...">[Series]</a></dd>
          ...
          <dt>Stats:</dt>
           <dd>
            Published: [Published]
            ...
           </dd>
         </dl>
         <h1>[Title]</h1>
         <div class="byline">by <a rel="author" href="...">[Author]</a>, [...]</div>
         <p>Summary</p>
         <blockquote class="userstuff"><p>[Summary]</p></blockquote>
         ...
        </div>
        ```
        """
        meta = soup.body.find("div", class_="meta")
        assert meta is not None

        title = meta.find("h1").get_text(strip=True)

        byline = meta.find("div", class_="byline")
        assert byline is not None
        # TODO: Handle pseuds in the author list.
        authors = [author.get_text(strip=True) for author in byline.find_all("a")]

        summary_heading = meta.find("p", string="Summary")
        assert summary_heading is not None
        summary = summary_heading.find_next_sibling(
            "blockquote", class_="userstuff"
        ).get_text("\n", strip=True)

        tags_section = meta.find("dl", class_="tags")
        assert tags_section is not None
        tags = ["Fanworks"]
        pubdate = None
        language = None
        series = None
        for dt in tags_section.find_all("dt"):
            dd = dt.find_next_sibling("dd")
            assert dd is not None
            label = dt.get_text(" ", strip=True).removesuffix(":")

            match label:
                case (
                    "Rating"
                    | "Archive Warning"
                    | "Archive Warnings"
                    | "Category"
                    | "Fandom"
                    | "Relationship"
                    | "Relationships"
                    | "Character"
                    | "Characters"
                    | "Additional Tags"
                ):
                    tags.extend(tag.get_text(strip=True) for tag in dd.find_all("a"))
                case "Language":
                    language_name = dd.get_text(strip=True)
                    language = langcodes.find(language_name).language
                case "Series":
                    series_link = dd.find("a")
                    assert series_link is not None
                    series_match = re.search(
                        r"Part\s+(\d+)\s+of", dd.get_text(" ", strip=True)
                    )
                    assert series_match is not None
                    series = (
                        series_link.get_text(strip=True),
                        int(series_match.group(1)),
                    )
                case "Stats":
                    stats_text = dd.get_text(" ", strip=True)
                    pubdate_match = re.search(
                        r"(Completed|Updated|Published):\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                        stats_text,
                    )
                    assert pubdate_match is not None
                    pubdate = date.fromisoformat(pubdate_match.group(2))

        assert pubdate is not None
        assert language is not None

        return cls(
            title=title,
            authors=authors,
            tags=tags,
            pubdate=pubdate,
            summary=summary,
            language=language,
            series=series,
        )

    def sortable_title(self) -> str:
        """Get the title of the work in a sortable format.

        See: https://github.com/otwcode/otwarchive/blob/1ba554cd19040c40c766c322d78d65c7b831f09d/app/models/work.rb#L1102-L1108
        """
        sortable_title = self.title.lower()
        sortable_title = re.sub(r'^[\'"\./]', "", sortable_title)
        sortable_title = re.sub(r"^(an?) (.*)", r"\2, \1", sortable_title)
        sortable_title = re.sub(r"^the (.*)", r"\1, the", sortable_title)
        if re.match(r"^\d", sortable_title):
            sortable_title = sortable_title.rjust(5, "0")
        return sortable_title

    def sortable_authors(self) -> str:
        """Get the authors of the work in a sortable format.

        See: https://github.com/otwcode/otwarchive/blob/1ba554cd19040c40c766c322d78d65c7b831f09d/app/models/work.rb#L1094-L1100
        """
        sortable_authors = ",  ".join(
            sorted(re.sub(AUTHOR_PSEUD_REGEX, "", author) for author in self.authors)
        ).lower()
        sortable_authors = re.sub(SORTED_AUTHOR_REGEX, "", sortable_authors)
        return sortable_authors


"""

  # A hash of the work data calibre needs
  def meta
    return @metadata if @metadata
    @metadata = {
      title:             work.title,
      sortable_title:    work.sorted_title,
      # Using ampersands as instructed by Calibre's ebook-convert documentation
      # hides all but the first author name in Books (formerly iBooks). The
      # other authors cannot be used for searching or sorting. Using commas
      # just means Calibre's GUI treats it as one name, e.g. "testy, testy2" is
      # like "Fangirl, Suzy Q", for searching and sorting.
      authors:           download.authors,
      sortable_authors:  work.authors_to_sort_on,
      # We add "Fanworks" because Books uses the first tag as the category and
      # it would otherwise be the work's rating, which is weird.
      tags:              "Fanworks, " + work.tags.pluck(:name).join(", "),
      pubdate:           work.revised_at.to_date.to_s,
      summary:           work.summary.to_s,
      language:          work.language.short
    }
    if work.series.exists?
      series = work.series.first
      @metadata[:series_title] = series.title
      @metadata[:series_position] = series.position_of(work).to_s
    end
    @metadata
  end
end
"""


def has_creator_style(soup: BeautifulSoup) -> bool:
    """Determine whether a creator style is applied.

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
    return work_nav_class.find("li", class_="style") is not None


def get_download_path(soup: BeautifulSoup, file_format: Format) -> str:
    """Get the path for downloading a work as the specified format.

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
    """Assert that the content of the provided response is an attachment.

    Returns the filename as a UTF-8 encoded string.
    """
    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment")

    charset, encoded_filename = re.search(
        r"filename\*\s*=\s*([^']+)''(.+)", content_disposition
    ).groups()

    # TODO: Fall back on filename if decoding error
    return unquote(encoded_filename, encoding=charset)


def get_work_skin(soup: BeautifulSoup) -> str:
    """Get the work skin from the inline HTML.

    The relevant location in the HTML is under the `work` div:
    ```html
    <div class="work">
     <!--work description, metadata, notes and messages-->
     ...
     <style type="text/css">
      ...
     </style>
     <!-- end cache for work skin -->
     <!-- BEGIN section where work skin applies -->
     <div id="workskin">
      ...
     </div>
     <!-- END work skin -->
    </div>
    ```
    """
    work_skin = soup.find("div", class_="work").find("style", {"type": "text/css"})

    # If we can't find the work skin, something has gone really wrong.
    assert work_skin.string is not None
    return work_skin.string


def get_user_page_count(soup: BeautifulSoup) -> int:
    """Get the number of pages in the user works navigation bar.

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
    """Get the ids of all the works listed in a user's page.

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


def inject_work_skin(soup: BeautifulSoup, css: str):
    """Inject a work skin inline. This mutates `soup`.

    The work skin CSS is inserted inside the style for the work:
    ```html
    <head>
     ...
     <style type="text/css">
      [css]
      p.message { text-align: center}
      ...
     </style>
    </head>
    ```

    Then the workskin class is injected for every chapter:
    ```html
    <div id="chapters" class="userstuff">
    ...
    <!--chapter content-->
     <div class="userstuff" [id="workskin"]>
     </div>
    ...
    <!--chapter content-->
     <div class="userstuff" [id="workskin"]>
     </div>
    </div>
    ```
    """
    # Inject CSS inline
    text_style = soup.head.find("style", {"type": "text/css"})
    text_style.string = f"{css}\n{text_style.string}"

    # Inject workskin class for every chapter
    user_text = soup.body.find("div", {"id": "chapters"})
    chapters = user_text.find_all("div", {"class": "userstuff"})
    for chapter in chapters:
        chapter["id"] = WORKSKIN_TAG
