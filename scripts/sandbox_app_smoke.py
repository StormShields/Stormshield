"""Starts the built Sandbox app from its zip, as CI's only test of the bundle.

Checks that no `.env` is inside and both Regions' Cache Packs are, that the Hub reports a Sandbox
with Sensors, that switching Region works on the bundled pack, and that Stop ends the process and
leaves no temp folder behind. Any failure exits non-zero with the app's log.

    uv run --project node python scripts/sandbox_app_smoke.py dist-sandbox-app/<zip>
"""

import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx

from storm_shield.cache_pack import RELEASED_PACKS, ZIP_NAME

APP_NAME = "Storm Shield Sandbox"
WINDOWS = sys.platform == "win32"
LOG_NAME = "storm-shield-sandbox.log"
TEMP_FOLDER_PREFIX = "storm-shield-sandbox-"
START_SECONDS = 180
STOP_SECONDS = 60


def bundle_problems(unpacked: Path) -> list[str]:
    """What is wrong with the unpacked download: a `.env` file in it, or a Region's pack missing."""
    problems = [
        f"{path.relative_to(unpacked)} must not be in the download"
        for path in unpacked.rglob(".env*")
        if path.name != ".env.example"
    ]
    for region in RELEASED_PACKS:
        if not any(unpacked.rglob(f"build/{region}/{ZIP_NAME}")):
            problems.append(f"the {region} Cache Pack is not in the download")
    return problems


def unpack(zip_path: Path, into: Path) -> Path:
    if sys.platform == "darwin":
        subprocess.run(["ditto", "-x", "-k", str(zip_path), str(into)], check=True)
        return into / f"{APP_NAME}.app" / "Contents" / "MacOS" / APP_NAME
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(into)
    return into / APP_NAME / f"{APP_NAME}.exe"


def wait_for_port(app: subprocess.Popen[bytes], log: Path) -> int:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if app.poll() is not None:
            raise SystemExit(f"the app ended on its own with exit code {app.returncode}")
        found = re.search(r"Sandbox dashboard: http://127\.0\.0\.1:(\d+)", _read(log))
        if found:
            return int(found.group(1))
        time.sleep(1)
    raise SystemExit("the app never said where its dashboard is")


def wait_until_answering(client: httpx.Client, base: str) -> None:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        try:
            client.get(f"{base}/api/state").raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(1)
    raise SystemExit("the dashboard never answered /api/state")


def check_running_app(client: httpx.Client, base: str) -> None:
    state = client.get(f"{base}/api/state").json()
    if not state.get("sandbox"):
        raise SystemExit(f"/api/state reports no sandbox: {state.get('sandbox')!r}")
    if not client.get(f"{base}/api/sandbox/nodes").json()["nodes"]:
        raise SystemExit("the Sandbox has no Sensors")
    regions = client.get(f"{base}/api/sandbox/regions").json()
    other = next(r["name"] for r in regions["regions"] if r["name"] != regions["current"])
    switched = client.post(f"{base}/api/sandbox/region", json={"region": other})
    if switched.status_code != 200 or switched.json()["current"] != other:
        raise SystemExit(f"switching to {other} failed: {switched.status_code} {switched.text}")


def stop(client: httpx.Client, base: str, app: subprocess.Popen[bytes]) -> None:
    # The Origin a page of the Sandbox's own sends; without it the route refuses.
    client.post(f"{base}/api/sandbox/stop", headers={"Origin": base}).raise_for_status()
    try:
        app.wait(STOP_SECONDS)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"Stop did not end the app within {STOP_SECONDS} s") from None


def _read(path: Path) -> str:
    return path.read_text(errors="replace") if path.is_file() else ""


def main(zip_path: Path) -> None:
    with tempfile.TemporaryDirectory() as work_dir:
        work = Path(work_dir)
        unpacked, temp = work / "unpacked", work / "temp"
        unpacked.mkdir()
        temp.mkdir()
        executable = unpack(zip_path, unpacked)
        problems = bundle_problems(unpacked)
        if problems:
            raise SystemExit("\n".join(problems))
        stub = "python -c pass" if WINDOWS else "python3 -c pass"
        # The app's temp folder is ours, so "the folder is gone" is a plain look inside it; and
        # `BROWSER` is how Python's `webbrowser` is told to open something else than a browser.
        env = {**os.environ, "BROWSER": stub, "TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp)}
        app = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL)
        log = temp / LOG_NAME
        try:
            base = f"http://127.0.0.1:{wait_for_port(app, log)}"
            with httpx.Client(timeout=30) as client:
                wait_until_answering(client, base)
                check_running_app(client, base)
                if "downloading the" in _read(log):
                    raise SystemExit("the app downloaded a Cache Pack instead of using its own")
                stop(client, base, app)
            left = [p.name for p in temp.iterdir() if p.name.startswith(TEMP_FOLDER_PREFIX)]
            if left:
                raise SystemExit(f"Stop left its temp folder behind: {left}")
        except BaseException:
            print(f"--- the app's log ---\n{_read(log)}")
            raise
        finally:
            if app.poll() is None:
                app.kill()
    print("smoke check passed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
