"""Where the app's own files live: the built dashboard and the Regions.

A repo checkout keeps them beside `node/`; a bundled app (PyInstaller) unpacks them under
`sys._MEIPASS`. Everything that needs one of these folders asks here, so the bundle needs no
other change.
"""

import sys
from pathlib import Path


def _app_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[3]


APP_ROOT = _app_root()
DASHBOARD_DIR = APP_ROOT / "dashboard" / "dist"
REGIONS_DIR = APP_ROOT / "regions"
