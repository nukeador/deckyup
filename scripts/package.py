#!/usr/bin/env python3
"""Deterministic allowlist packaging, with no publishing side effects."""

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package(output, version=None, fixture=None):
    files = [
        ROOT / name
        for name in (
            "plugin.json",
            "package.json",
            "main.py",
            "dist/index.js",
            "LICENSE",
            "README.md",
        )
    ]
    files += sorted((ROOT / "direct_updater").rglob("*.py"))
    files.append(ROOT / "direct_updater/_html/LICENSE")
    prefix = "decky-direct-updater/"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            data = path.read_bytes()
            if version and path.name in ("package.json", "plugin.json"):
                manifest = json.loads(data)
                manifest["version"] = version
                data = (json.dumps(manifest, indent=2) + "\n").encode()
            if fixture and path.name == "main.py":
                data = data.replace(
                    b"from direct_updater.plugin_updates import Updater",
                    b"from direct_updater.fixture_backend import FixtureUpdater as Updater",
                )
            entry = zipfile.ZipInfo(
                prefix + path.relative_to(ROOT).as_posix(), (2024, 1, 1, 0, 0, 0)
            )
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
        if fixture:
            archive.writestr(prefix + "direct_updater/fixture_backend.py", fixture)
    return output


if __name__ == "__main__":
    print(
        package(
            sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist-release/Decky-Direct-Updater.zip"
        )
    )
