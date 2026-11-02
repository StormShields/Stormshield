"""The Sandbox as a double-clickable app: no arguments, and any problem ends up on a page.

Someone who opens it has no terminal, so it picks the port itself, opens the dashboard of a
Sandbox that is already running instead of starting a second one, logs to a file in the temp
folder and, when it cannot start, opens a page that says why.
"""

import html
import logging
import socket
import sys
import tempfile
import traceback
import webbrowser
from pathlib import Path

import httpx

from storm_shield.settings import Settings

logger = logging.getLogger(__name__)

LOOPBACK_HOST = "127.0.0.1"
PREFERRED_PORT = 8000
LOG_FILE_NAME = "storm-shield-sandbox.log"
FAILURE_PAGE_NAME = "storm-shield-sandbox-failed.html"


def log_file() -> Path:
    return Path(tempfile.gettempdir()) / LOG_FILE_NAME


def sandbox_is_running_on(port: int) -> bool:
    try:
        state = httpx.get(f"http://{LOOPBACK_HOST}:{port}/api/state", timeout=2).json()
        return bool(state["sandbox"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return False


def _bindable(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind((LOOPBACK_HOST, port))
        except OSError:
            return False
    return True


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((LOOPBACK_HOST, 0))
        return int(probe.getsockname()[1])


class _LastServerError(logging.Handler):
    """Remembers uvicorn's last error line: when it cannot bind it exits with just a number, and
    the reason ("address already in use") is only in what it logged."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.message = ""

    def emit(self, record: logging.LogRecord) -> None:
        self.message = record.getMessage()


def _reason(error: BaseException, server_error: str) -> str:
    if isinstance(error, SystemExit):
        return server_error or f"the server stopped while starting (exit code {error.code})"
    return str(error) or type(error).__name__


def write_failure_page(reason: str, log: Path) -> Path:
    # A fresh folder, so a file planted at a predictable name in the shared temp folder is not followed.
    page = Path(tempfile.mkdtemp(prefix="storm-shield-")) / FAILURE_PAGE_NAME
    page.write_text(
        "<!doctype html><meta charset=utf-8><title>Storm Shield Sandbox could not start</title>"
        "<h1>Storm Shield Sandbox could not start</h1>"
        f"<p>{html.escape(reason)}</p>"
        f"<p>The full log is at <code>{html.escape(str(log))}</code></p>",
        encoding="utf-8",
    )
    return page


def main() -> None:
    log = log_file()
    logging.basicConfig(level=logging.INFO, filename=log, force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    last_server_error = _LastServerError()
    logging.getLogger("uvicorn.error").addHandler(last_server_error)
    port = PREFERRED_PORT
    # Whatever went wrong, the person double-clicking has no terminal: it all has to reach the page.
    # That includes importing the Sandbox, which reads its Region, and uvicorn exiting with
    # SystemExit when it cannot bind.
    try:
        if sandbox_is_running_on(PREFERRED_PORT):
            webbrowser.open(f"http://{LOOPBACK_HOST}:{PREFERRED_PORT}")
            return
        from storm_shield.sandbox import serve

        port = PREFERRED_PORT if _bindable(PREFERRED_PORT) else free_port()
        serve(port, Settings().region)
    except (Exception, SystemExit) as error:  # noqa: BLE001
        logger.error("the Sandbox could not start\n%s", traceback.format_exc())
        # Two quick launches both find 8000 free and the slower one loses the bind: the winner is
        # the Sandbox to open.
        if port == PREFERRED_PORT and sandbox_is_running_on(PREFERRED_PORT):
            webbrowser.open(f"http://{LOOPBACK_HOST}:{PREFERRED_PORT}")
            return
        reason = _reason(error, last_server_error.message)
        webbrowser.open(write_failure_page(reason, log).as_uri())
        sys.exit(1)
