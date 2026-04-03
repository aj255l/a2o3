"""TODO: Centralize AO3 request error handling here.

Implementation plan and requirements:

- Add a dedicated archive error layer that centralizes AO3 request handling,
  user-facing messages, and retry behavior.
- Define custom exceptions for:
  - flood control / retry exhausted
  - resource not found
  - authentication failure
  - generic AO3 request failure
  - network/timeout failure
- Add request helper(s) in this module to wrap requests.Session.get and
  requests.Session.post and translate failures into those exceptions.
- Add a content-check helper in this module for AO3 HTML error pages that
  detects the text "Sorry, we couldn't find the work you were looking for"
  inside an error container.
- Match a div whose classes include "error" and "flash".
- Route both the login-page GET and login POST through the new helper layer.
- Route every AO3 request in the archive flow through the new helper layer:
  - work page fetch
  - user works page fetch
  - download fetches

Error-handling behavior:

- Flood control:
  - Detect AO3 flood control from the HTTP response body or page text in the
    wrapper layer.
  - Print a clear user-facing message that flood control was hit and the
    command will retry in 5 minutes.
  - Sleep 5 minutes, retry once, then fail with a flood-control exception if
    it happens again.
- 404 handling:
  - The wrapper accepts a custom not-found message.
  - Use work-specific text for work fetches/downloads.
  - Use user-specific text for user works pages.
  - Bubble the custom exception to the top-level command so the CLI exits
    cleanly with the message.
- Missing-work HTML page:
  - After a successful work-page fetch, inspect the parsed HTML for the AO3
    missing-work message in the error container.
  - Treat that exactly like a nonexistent work and raise the same not-found
    exception.
- Authentication failure:
  - If login returns HTTP 403, raise an authentication exception with a message
    that the AO3 username/password is incorrect.
  - Keep the existing authenticity_token extraction failure as a distinct AO3
    request/configuration failure with a cleaner message.
- Network failures:
  - Catch requests connection and timeout exceptions in the wrapper and raise a
    user-facing network failure exception telling the user to retry and check
    connectivity.
- Generic unexpected HTTP failures:
  - Convert any remaining requests.HTTPError into a generic AO3 request failure
    that includes the operation context, status code, and URL when available.

Other request error cases to cover:

- Login page GET can fail before credentials are even submitted.
- Download endpoints can fail independently of the initial work page fetch if a
  work is deleted or access changes mid-run.
- User pagination requests after page 1 can fail and should surface as
  user-page errors, not raw tracebacks.
- AO3 can return HTML error pages with status 200, so content checks must not
  rely only on status codes.
- requests transport errors like timeout, connection reset, or DNS failure
  should be translated into clean CLI errors.
- Missing or malformed attachment headers on download are adjacent to request
  handling; do not change that behavior in this task unless it currently
  produces a raw traceback during normal request failures.

User requirements:

- AO3 has flood control. Most of the time we should just retry in a few
  minutes, and print to the user that we hit flood control.
- If we get a 404, we should completely fail and say that the work doesn't
  exist, or if fetching the user page, that the user doesn't exist.
- The 404 handler should take in a custom message.
- If we get a "Sorry, we couldn't find the work you were looking for" message
  under a div classed as flash error, we should also say the work doesn't
  exist.
- If we fail to log in, meaning we get a 403 during authentication, we should
  print an error message about how the credentials are wrong.
"""

import time

import requests

FLOOD_CONTROL_DELAY_SECONDS = 5 * 60
FLOOD_CONTROL_TEXT = (
    "retry later",
    "too many requests",
)


class ArchiveError(Exception):
    """Base class for clean user-facing archive failures."""

    def __str__(self) -> str:
        message = super().__str__()
        original_error = get_original_error(self)
        if original_error is None:
            return message
        return (
            f"{message} "
            f"(original error: {type(original_error).__name__}: {original_error})"
        )


def get_original_error(exc: BaseException) -> BaseException | None:
    """Get the deepest non-ArchiveError cause, if there is one."""
    current_exc = exc.__cause__ or exc.__context__
    original_error = None
    while current_exc is not None:
        if not isinstance(current_exc, ArchiveError):
            original_error = current_exc
        current_exc = current_exc.__cause__ or current_exc.__context__
    return original_error


class AO3NotFoundError(ArchiveError):
    """Requested AO3 resource does not exist."""


class AO3AuthenticationError(ArchiveError):
    """AO3 rejected the provided login credentials."""


class AO3FloodControlError(ArchiveError):
    """AO3 flood control persisted after retry."""


def get_flood_control_reason(response: requests.Response) -> str | None:
    """Return the flood-control trigger that matched this response, if any."""
    if response.status_code in (403, 429, 500, 525):
        return f"HTTP {response.status_code}"

    response_text = response.text.lower()
    for marker in FLOOD_CONTROL_TEXT:
        if marker in response_text:
            return f"matched '{marker}'"
    return None


def is_connection_reset_error(exc: requests.ConnectionError) -> bool:
    """Return whether this connection failure looks like a connection reset."""
    current_exc = exc
    # requests usually wraps the underlying socket failure, so walk the cause
    # chain until we either find ConnectionResetError or run out of exceptions.
    while current_exc is not None:
        if isinstance(current_exc, ConnectionResetError):
            return True
        current_exc = current_exc.__cause__ or current_exc.__context__
    return False


def request(
    session: requests.Session,
    method: str,
    url: str,
    spinner=None,
    **request_kwargs,
) -> requests.Response:
    """Send an AO3 request and translate 404s into a user-facing error."""
    response = session.request(method, url, **request_kwargs)
    flood_control_reason = get_flood_control_reason(response)
    if flood_control_reason is not None:
        # First probable flood control hit: retry once immediately without
        # surfacing anything to the user.
        response = session.request(method, url, **request_kwargs)
        flood_control_reason = get_flood_control_reason(response)
        if flood_control_reason is not None:
            # Second probable flood control hit: tell the user, wait 5 minutes,
            # and then try one final time.
            message = (
                f"This is probably AO3 flood control ({flood_control_reason}). "
                "Waiting 5 minutes, then retrying once."
            )
            if spinner is not None:
                spinner.write(message)
            else:
                print(message)
            time.sleep(FLOOD_CONTROL_DELAY_SECONDS)

            try:
                response = session.request(method, url, **request_kwargs)
            except requests.ConnectionError as exc:
                if not is_connection_reset_error(exc):
                    raise
                # AO3 or an intermediary may drop the idle keep-alive
                # connection while we wait 5 minutes, so retry once on the
                # same session if the first post-sleep request gets reset.
                if spinner is not None:
                    spinner.write(
                        "AO3 connection was reset after waiting. Retrying once."
                    )
                else:
                    print("AO3 connection was reset after waiting. Retrying once.")
                response = session.request(method, url, **request_kwargs)
            flood_control_reason = get_flood_control_reason(response)
            if flood_control_reason is not None:
                # Third probable flood control hit: give up and surface the
                # last matching trigger to the user.
                raise AO3FloodControlError(
                    "Error fetching from AO3: "
                    "probable flood control persisted after retry "
                    f"({flood_control_reason})."
                )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        if response.status_code == 404:
            raise AO3NotFoundError() from exc
        raise

    return response
