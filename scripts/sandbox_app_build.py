"""Builds the Sandbox app for the platform this runs on: one folder PyInstaller makes, zipped.

It holds Python, the Node package, the built dashboard, `regions/` and the current Cache Pack of
each built-in Region, so the app downloads nothing on its first run. PyInstaller cannot
cross-build, so each platform runs this on its own machine (.github/workflows/sandbox-app.yml).

    uv run --project node --with "pyinstaller>=6,<7" python scripts/sandbox_app_build.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from storm_shield.cache_pack import RELEASED_PACKS, ZIP_NAME, release_url

REPO = Path(__file__).resolve().parents[1]
APP_NAME = "Storm Shield Sandbox"
ENTRY_POINT = REPO / "scripts" / "sandbox_app_entry.py"
OUTPUT = REPO / "dist-sandbox-app"
MAC = sys.platform == "darwin"
PLATFORM = "macos-arm64" if MAC else "windows-x64"
ZIP_PATH = OUTPUT / f"Storm-Shield-Sandbox-{PLATFORM}.zip"


def download_packs(into: Path) -> None:
    """Each built-in Region's published pack, laid out where the Sandbox looks for a built one."""
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for region in RELEASED_PACKS:
            response = client.get(str(release_url(region)))
            response.raise_for_status()
            pack = into / "node" / "build" / region / ZIP_NAME
            pack.parent.mkdir(parents=True)
            pack.write_bytes(response.content)


def bundle(packs: Path) -> Path:
    dashboard = REPO / "dashboard" / "dist"
    if not (dashboard / "index.html").is_file():
        raise SystemExit("build the dashboard first: cd dashboard && pnpm install && pnpm build")
    work = OUTPUT / "work"
    # Only these folders go in: nothing else of the checkout, so nothing like a `.env` can.
    data = [
        (dashboard, "dashboard/dist"),
        (REPO / "regions", "regions"),
        (packs / "node" / "build", "node/build"),
    ]
    command = [
        sys.executable, "-m", "PyInstaller", str(ENTRY_POINT),
        "--noconfirm", "--clean", "--windowed", "--name", APP_NAME,
        "--distpath", str(OUTPUT / "dist"), "--workpath", str(work), "--specpath", str(work),
        "--paths", str(REPO / "node" / "src"),
        # Reached by name at run time (uvicorn's loops, Reticulum's interfaces), so not found by
        # reading the imports.
        "--collect-submodules", "storm_shield",
        "--collect-submodules", "uvicorn",
        "--collect-all", "RNS",
    ]  # fmt: skip
    for source, inside in data:
        command += ["--add-data", f"{source}{';' if sys.platform == 'win32' else ':'}{inside}"]
    subprocess.run(command, check=True)
    return OUTPUT / "dist" / (f"{APP_NAME}.app" if MAC else APP_NAME)


def zip_bundle(built: Path) -> None:
    ZIP_PATH.unlink(missing_ok=True)
    if MAC:
        # `ditto` keeps the symlinks and permissions a .app needs; `zip` modules do not.
        subprocess.run(
            ["ditto", "-c", "-k", "--keepParent", str(built), str(ZIP_PATH)], check=True
        )
    else:
        base = str(ZIP_PATH.with_suffix(""))
        shutil.make_archive(base, "zip", built.parent, built.name)


def main() -> None:
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir()
    with tempfile.TemporaryDirectory() as packs:
        download_packs(Path(packs))
        zip_bundle(bundle(Path(packs)))
    print(f"built {ZIP_PATH}")


if __name__ == "__main__":
    main()
