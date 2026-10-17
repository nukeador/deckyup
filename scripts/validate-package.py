#!/usr/bin/env python3
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from direct_updater.package_validation import validate_package

root = Path(__file__).resolve().parents[1]
package = json.loads((root / "package.json").read_text())
filename = sys.argv[1]
version = sys.argv[2] if len(sys.argv) > 2 else package["version"]
result = validate_package(filename, "Decky Direct Updater", version)
with zipfile.ZipFile(filename) as archive:
    names = archive.namelist()
    if any("fixture_backend" in name for name in names):
        raise SystemExit("Fixture backend found in production package")
    if b"FixtureUpdater" in archive.read(result["root"] + "/main.py"):
        raise SystemExit("Fixture entry point found in production package")
    for required in (
        "main.py",
        "LICENSE",
        "README.md",
        "direct_updater/plugin_updates.py",
        "direct_updater/_html/parser.py",
        "direct_updater/_html/__init__.py",
        "direct_updater/_html/entities.py",
        "direct_updater/_html/_markupbase.py",
        "direct_updater/_html/LICENSE",
    ):
        if result["root"] + "/" + required not in names:
            raise SystemExit("Missing " + required)
    if any(
        any(
            part in {"tests", ".git", "__pycache__", "node_modules", "fixtures"}
            for part in Path(name).parts
        )
        for name in names
    ):
        raise SystemExit("Development content found in package")
print(f"Valid Decky ZIP: {filename} ({len(names)} files, version {version})")
