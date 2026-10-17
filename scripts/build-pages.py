#!/usr/bin/env python3
"""Build a static site with the checksum-verified, published stable installer."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from direct_updater.github_releases import SafeRedirect, check_download_url
from direct_updater.package_validation import MAX_DOWNLOAD
from direct_updater.tls import github_ssl_context
from direct_updater.versions import Version
from scripts.site_locales import render_pages

REPOSITORY = "nukeador/decky-direct-updater"
LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET = "Decky-Direct-Updater.zip"
IMAGES = ("updates.png", "plugin-details.png", "find-plugins.png")


def download(url, destination, limit):
    check_download_url(url)
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=github_ssl_context()), SafeRedirect()
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Decky-Direct-Updater-Pages"})
    with opener.open(request, timeout=30) as response, destination.open("wb") as stream:
        check_download_url(response.geturl())
        size = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("Release download exceeded its size limit")
            stream.write(chunk)


def release_assets(release):
    if (
        not isinstance(release, dict)
        or release.get("draft") is not False
        or release.get("prerelease") is not False
    ):
        raise ValueError("Latest release must be published and stable")
    tag = release.get("tag_name", "")
    version = Version(tag)
    if version.pre:
        raise ValueError("Prereleases cannot be the public installer")
    if not isinstance(release.get("assets"), list):
        raise ValueError("Release assets unavailable")
    urls = {}
    for name in (ASSET, "SHA256SUMS"):
        matches = [a for a in release["assets"] if isinstance(a, dict) and a.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"Release must contain exactly one {name}")
        url = matches[0].get("browser_download_url")
        expected = f"https://github.com/{REPOSITORY}/releases/download/{urllib.parse.quote(tag, safe='')}/{name}"
        if url != expected:
            raise ValueError("Unexpected release asset location")
        urls[name] = url
    return version.text, urls


def verify_checksum(archive, checksums):
    matches = []
    for line in checksums.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *](.+)", line)
        if match and match[2] == ASSET:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise ValueError("Checksum file must identify exactly one installable ZIP")
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != matches[0]:
        raise ValueError("Release ZIP checksum does not match SHA256SUMS")
    return matches[0]


def build(output=None, fetch=download):
    output = Path(output or ROOT / "_site").resolve()
    if output.name != "_site" or output == ROOT:
        raise ValueError("Generated output must be a dedicated _site directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pages-", dir=output.parent) as temporary:
        work = Path(temporary)
        metadata = work / "release.json"
        fetch(LATEST, metadata, 1024 * 1024)
        version, urls = release_assets(json.loads(metadata.read_text(encoding="utf-8")))
        archive, checksums = work / ASSET, work / "SHA256SUMS"
        fetch(urls[ASSET], archive, MAX_DOWNLOAD)
        fetch(urls["SHA256SUMS"], checksums, 64 * 1024)
        digest = verify_checksum(archive, checksums)
        # Run our validator, never anything from inside the downloaded archive.
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate-package.py"), str(archive), version],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ValueError("Published release ZIP failed Decky package validation")
        prepared = work / "site"
        shutil.copytree(
            ROOT / "site", prepared, ignore=shutil.ignore_patterns("index.html", "locales")
        )
        render_pages(ROOT / "site", prepared)
        (prepared / "images").mkdir()
        for image in IMAGES:
            shutil.copyfile(ROOT / "docs/images" / image, prepared / "images" / image)
        shutil.copyfile(archive, prepared / "install.zip")
        (prepared / ".nojekyll").touch()
        if output.is_symlink():
            raise ValueError("Generated output cannot be a symbolic link")
        if output.exists():
            shutil.rmtree(output)
        prepared.replace(output)
    print(f"Built {output}: stable {version}, install.zip SHA256 {digest}")
    return {"version": version, "sha256": digest, "output": str(output)}


if __name__ == "__main__":
    try:
        build()
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit(f"Pages build failed: {error}") from error
