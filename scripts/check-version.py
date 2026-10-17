#!/usr/bin/env python3
"""Validate metadata and an optional deliberately selected release tag."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from direct_updater.versions import Version

root = Path(__file__).resolve().parents[1]
package = json.loads((root / "package.json").read_text())
plugin = json.loads((root / "plugin.json").read_text())
version = package["version"]
parsed = Version(version)
if parsed.pre or parsed.text != version or plugin["version"] != version:
    raise SystemExit("Package and plugin versions must match a stable x.y.z version")
if len(sys.argv) > 1 and sys.argv[1] != "v" + version:
    raise SystemExit("Release tag must match package.json and plugin.json")
print(version)
