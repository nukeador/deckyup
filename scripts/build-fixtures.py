#!/usr/bin/env python3
"""Build isolated local hardware fixtures after the normal frontend build."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("packaging", ROOT / "scripts/package.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output = ROOT / "dist-release/local-fixture"
fixture = (ROOT / "scripts/fixture_backend.py.txt").read_bytes()
for version in ("0.1.0", "0.1.1"):
    module.package(output / f"Decky-Direct-Updater-v{version}.zip", version, fixture)
release = [
    {
        "id": 101,
        "tag_name": "v0.1.1",
        "draft": False,
        "prerelease": False,
        "assets": [{"id": 201, "name": "Decky-Direct-Updater-v0.1.1.zip"}],
    }
]
(output / "release.json").write_text(json.dumps(release, indent=2) + "\n")
print(f"LOCAL TEST ONLY: {output}")
