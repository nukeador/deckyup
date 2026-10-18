#!/usr/bin/env python3
"""Build local fixtures with frontend and manifest versions kept in sync."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("packaging", ROOT / "scripts/package.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
output = ROOT / "dist-release/local-fixture"
fixture = (ROOT / "scripts/fixture_backend.py.txt").read_bytes()
manifests = {path: path.read_bytes() for path in (ROOT / "package.json", ROOT / "plugin.json")}
try:
    for version in ("0.1.0", "0.1.1"):
        for path, original in manifests.items():
            data = json.loads(original)
            data["version"] = version
            path.write_text(json.dumps(data, indent=2) + "\n")
        subprocess.run(["pnpm", "build"], cwd=ROOT, check=True)
        module.package(output / f"Decky-Direct-Updater-v{version}.zip", version, fixture)
finally:
    for path, original in manifests.items():
        path.write_bytes(original)
    subprocess.run(["pnpm", "build"], cwd=ROOT, check=True)

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
