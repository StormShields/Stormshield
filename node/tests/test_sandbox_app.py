import logging
import os
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from storm_shield import app_files, sandbox_app
from storm_shield import sandbox as sandbox_module
from storm_shield.sandbox import sandbox_server_config
from storm_shield.settings import LOOPBACK_HOST

_log = logging.getLogger("storm_shield.sandbox_app")


class _Answers(BaseHTTPRequestHandler):
    body = b'{"sandbox": {"anything": 1}}'

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _serving(body: bytes) -> tuple[HTTPServer, int]:
    handler = type("Handler", (_Answers,), {"body": body})
    server = HTTPServer((LOOPBACK_HOST, 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    urls: list[str] = []

    def record(url: str) -> bool:
        urls.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", record)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return urls


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    ports: list[int] = []
    monkeypatch.setattr(sandbox_module, "serve", lambda port, region: ports.append(port))
    return ports


def _prefer(monkeypatch: pytest.MonkeyPatch, port: int) -> None:
    monkeypatch.setattr(sandbox_app, "PREFERRED_PORT", port)


def test_a_running_sandbox_is_opened_and_no_second_is_started(
    monkeypatch: pytest.MonkeyPatch, opened: list[str], started: list[int]
) -> None:
    server, port = _serving(b'{"sandbox": {"nodes": 5}}')
    _prefer(monkeypatch, port)
    sandbox_app.main()
    server.shutdown()
    assert opened == [f"http://127.0.0.1:{port}"]
    assert started == []


def test_something_else_on_the_port_leaves_the_port_alone_and_serves_elsewhere(
    monkeypatch: pytest.MonkeyPatch, opened: list[str], started: list[int]
) -> None:
    server, port = _serving(b'{"sandbox": null}')
    _prefer(monkeypatch, port)
    sandbox_app.main()
    server.shutdown()
    assert len(started) == 1 and started[0] not in (0, port)
    assert opened == []


def test_a_free_preferred_port_is_used(
    monkeypatch: pytest.MonkeyPatch, opened: list[str], started: list[int]
) -> None:
    port = sandbox_app.free_port()
    _prefer(monkeypatch, port)
    sandbox_app.main()
    assert started == [port]


def test_a_start_failure_opens_a_page_with_the_error_and_the_logs_path(
    monkeypatch: pytest.MonkeyPatch, opened: list[str], tmp_path: Path
) -> None:
    def fail(port: int, region: str) -> None:
        raise RuntimeError("no <Cache Pack> here")

    monkeypatch.setattr(sandbox_module, "serve", fail)
    _prefer(monkeypatch, sandbox_app.free_port())
    with pytest.raises(SystemExit):
        sandbox_app.main()
    (page_url,) = opened
    page = Path(page_url.removeprefix("file://")).read_text()
    assert "no &lt;Cache Pack&gt; here" in page
    assert str(tmp_path / sandbox_app.LOG_FILE_NAME) in page


def test_a_port_that_cannot_be_bound_still_opens_the_failure_page(
    monkeypatch: pytest.MonkeyPatch, opened: list[str]
) -> None:
    def cannot_bind(port: int, region: str) -> None:
        raise SystemExit(1)

    monkeypatch.setattr(sandbox_module, "serve", cannot_bind)
    _prefer(monkeypatch, sandbox_app.free_port())
    with pytest.raises(SystemExit):
        sandbox_app.main()
    (page_url,) = opened
    assert "exit code 1" in Path(page_url.removeprefix("file://")).read_text()


def test_a_bind_lost_to_a_sandbox_that_just_started_opens_that_sandbox(
    monkeypatch: pytest.MonkeyPatch, opened: list[str]
) -> None:
    server, port = _serving(b'{"sandbox": {"nodes": 5}}')
    _prefer(monkeypatch, port)
    answers = iter([False, True])
    monkeypatch.setattr(sandbox_app, "sandbox_is_running_on", lambda _port: next(answers))
    monkeypatch.setattr(sandbox_app, "_bindable", lambda _port: True)

    def lost_the_race(port: int, region: str) -> None:
        raise SystemExit(3)

    monkeypatch.setattr(sandbox_module, "serve", lost_the_race)
    sandbox_app.main()
    server.shutdown()
    assert opened == [f"http://127.0.0.1:{port}"]


def test_the_servers_own_reason_for_not_binding_is_on_the_page(
    monkeypatch: pytest.MonkeyPatch, opened: list[str]
) -> None:
    def cannot_bind(port: int, region: str) -> None:
        logging.getLogger("uvicorn.error").error("address already in use")
        raise SystemExit(3)

    monkeypatch.setattr(sandbox_module, "serve", cannot_bind)
    _prefer(monkeypatch, sandbox_app.free_port())
    with pytest.raises(SystemExit):
        sandbox_app.main()
    (page_url,) = opened
    assert "address already in use" in Path(page_url.removeprefix("file://")).read_text()


def test_a_region_that_cannot_be_read_opens_the_failure_page_through_the_real_entry_point(
    tmp_path: Path,
) -> None:
    opened_url = tmp_path / "opened-url"
    program = (
        "import webbrowser\n"
        f"webbrowser.open = lambda url: open({str(opened_url)!r}, 'w').write(url)\n"
        "from storm_shield import sandbox_app\n"
        "sandbox_app.main()\n"
    )
    environment = {**os.environ, "NODE_REGION": "nowhere", "TMPDIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", program],
        check=False,
        env=environment,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 1
    page = Path(opened_url.read_text().removeprefix("file://")).read_text()
    assert "nowhere" in page
    assert str(tmp_path / sandbox_app.LOG_FILE_NAME) in page
    assert "nowhere" in (tmp_path / sandbox_app.LOG_FILE_NAME).read_text()


def test_the_app_logs_to_a_file_in_the_temp_folder(
    monkeypatch: pytest.MonkeyPatch, opened: list[str], started: list[int], tmp_path: Path
) -> None:
    _prefer(monkeypatch, sandbox_app.free_port())
    monkeypatch.setattr(sandbox_module, "serve", lambda port, region: _log.info("serving"))
    sandbox_app.main()
    logging.shutdown()
    assert "serving" in (tmp_path / sandbox_app.LOG_FILE_NAME).read_text()


def test_the_sandbox_binds_loopback_only() -> None:
    config = sandbox_server_config(object(), 8000)
    assert config.host == "127.0.0.1"
    assert config.log_config is None


def test_the_dashboard_and_regions_are_found_beside_the_checkout() -> None:
    assert (app_files.REGIONS_DIR / "nepal" / "region.json").is_file()
    assert app_files.DASHBOARD_DIR == app_files.APP_ROOT / "dashboard" / "dist"


def test_a_bundled_app_finds_them_in_its_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert app_files._app_root() == tmp_path
