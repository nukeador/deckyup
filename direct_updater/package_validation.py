"""Inspect archives without extracting or executing their contents."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .github_releases import SafeRedirect, check_download_url
from .versions import Version
from .tls import github_ssl_context

MAX_DOWNLOAD = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
MAX_FILES = 30000
MAX_MANIFEST = 1024 * 1024


def validate_package(path, name, version, expected_root=None, expected_package_name=None):
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > MAX_FILES:
                raise ValueError("Empty archive or too many files")
            total = 0
            seen = set()
            roots = set()
            for entry in entries:
                text = entry.filename
                if "\x00" in entry.orig_filename:
                    raise ValueError("Unsafe ZIP path")
                parts = PurePosixPath(text).parts
                if (
                    not parts
                    or text.startswith("/")
                    or "\\" in text
                    or "\x00" in text
                    or any(
                        part in ("", "..", ".") or ":" in part
                        for part in text.rstrip("/").split("/")
                    )
                ):
                    raise ValueError("Unsafe ZIP path")
                normalized = "/".join(parts).casefold()
                if normalized in seen:
                    raise ValueError("Duplicate ZIP entry")
                seen.add(normalized)
                roots.add(parts[0])
                mode = entry.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("Links and special files are not supported")
                if entry.flag_bits & 1:
                    raise ValueError("Encrypted ZIP is not supported")
                total += entry.file_size
                if total > MAX_EXPANDED or (
                    entry.file_size > 10 * 1024 * 1024
                    and entry.file_size > max(1, entry.compress_size) * 250
                ):
                    raise ValueError("Suspicious extraction size")
            paths = {entry.filename.rstrip("/"): entry.is_dir() for entry in entries}
            for filename in paths:
                for parent in PurePosixPath(filename).parents:
                    if str(parent) in paths and not paths[str(parent)]:
                        raise ValueError("ZIP file conflicts with a parent directory")
            if len(roots) != 1:
                raise ValueError("Expected one top-level plugin directory")
            root = roots.pop()
            if expected_root is not None and root != expected_root:
                raise ValueError("ZIP folder differs from installed plugin; update manually")
            if not root or root.startswith("."):
                raise ValueError("Invalid plugin folder")
            required = [
                f"{root}/{file}" for file in ("plugin.json", "package.json", "dist/index.js")
            ]
            if any(file not in archive.namelist() for file in required):
                raise ValueError("Missing Decky package files")
            for filename in archive.namelist():
                if (
                    filename.endswith(("/plugin.json", "/package.json"))
                    and filename not in required[:2]
                ):
                    # Nested package.json is common in bundled dependencies; plugin manifests are not.
                    if filename.endswith("/plugin.json"):
                        raise ValueError("Duplicate plugin manifest")
            manifests = []
            for filename in required[:2]:
                if archive.getinfo(filename).file_size > MAX_MANIFEST:
                    raise ValueError("Oversized manifest")
                manifests.append(json.loads(archive.read(filename)))
            manifest, package = manifests
            if not isinstance(manifest, dict) or not isinstance(package, dict):
                raise ValueError("Invalid manifest objects")
            if manifest.get("name") != name:
                raise ValueError("ZIP plugin name does not match the installed plugin")
            if (
                expected_package_name is not None
                and package.get("name", "") != expected_package_name
            ):
                raise ValueError("ZIP package identity does not match the installed plugin")
            if Version(package.get("version", "")) != Version(version):
                raise ValueError("ZIP version does not match the selected release")
            if manifest.get("version") and Version(manifest["version"]) != Version(version):
                raise ValueError("Conflicting manifest versions")
            if not archive.getinfo(required[2]).file_size:
                raise ValueError("Empty frontend")
            if archive.testzip() is not None:
                raise ValueError("Corrupt ZIP contents")
            return {
                "root": root,
                "version": package["version"],
                "expanded_size": total,
                "package_name": package.get("name", ""),
            }
    except (
        zipfile.BadZipFile,
        KeyError,
        TypeError,
        UnicodeError,
        RuntimeError,
        NotImplementedError,
    ) as error:
        raise ValueError("Invalid Decky ZIP archive") from error


def repack_for_installed_folder(path, name, version, folder, expected_package_name=None):
    if not folder or folder in (".", "..") or any(c in folder for c in ("/", "\\", "\0")):
        raise ValueError("Invalid installed plugin folder")
    info = validate_package(path, name, version, expected_package_name=expected_package_name)
    if info["root"] == folder:
        return
    descriptor, replacement = tempfile.mkstemp(
        prefix=".repack-", suffix=".zip", dir=Path(path).parent
    )
    os.close(descriptor)
    try:
        with (
            zipfile.ZipFile(path) as source,
            zipfile.ZipFile(replacement, "w", zipfile.ZIP_DEFLATED) as target,
        ):
            for entry in source.infolist():
                filename = folder + entry.filename[len(info["root"]) :]
                output = zipfile.ZipInfo(filename, entry.date_time)
                output.compress_type = zipfile.ZIP_DEFLATED
                output.external_attr = entry.external_attr
                with source.open(entry) as stream, target.open(output, "w") as destination:
                    shutil.copyfileobj(stream, destination, 1024 * 1024)
        if Path(replacement).stat().st_size > MAX_DOWNLOAD:
            raise ValueError("Repacked update exceeds download size limit")
        validate_package(replacement, name, version, folder, expected_package_name)
        os.replace(replacement, path)
    finally:
        Path(replacement).unlink(missing_ok=True)


def cleanup_staged(directory):
    for path in Path(directory).glob("update-*.zip"):
        if (
            not path.is_symlink()
            and path.is_file()
            and time.time() - path.stat().st_mtime > 24 * 60 * 60
        ):
            path.unlink(missing_ok=True)


def stage_download(
    asset, repo, name, version, directory, expected_root=None, expected_package_name=None
):
    url = asset.get("browser_download_url", "")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.netloc != "github.com"
        or not parsed.path.startswith(f"/{repo}/releases/download/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Asset does not belong to the selected repository release")
    check_download_url(url)
    size = asset.get("size", 0)
    if size is not None and (not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD):
        raise ValueError("Release download exceeds the 512 MiB limit or has unknown size")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    cleanup_staged(directory)
    if shutil.disk_usage(directory).free < (size or MAX_DOWNLOAD) + MAX_EXPANDED + 64 * 1024 * 1024:
        raise ValueError("Not enough free disk space to safely stage and install this update")
    descriptor, temporary = tempfile.mkstemp(prefix="update-", suffix=".zip", dir=directory)
    digest = hashlib.sha256()
    written = 0
    deadline = time.monotonic() + 10 * 60
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Decky-Direct-Updater/0.1"})
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=github_ssl_context()), SafeRedirect()
        )
        with os.fdopen(descriptor, "wb") as target, opener.open(request, timeout=45) as response:
            check_download_url(response.geturl())
            length = response.headers.get("Content-Length")
            if length is not None:
                declared = int(length)
                if not 0 < declared <= MAX_DOWNLOAD or (size is not None and declared != size):
                    raise ValueError(
                        "Download length exceeds limit or differs from release metadata"
                    )
                size = declared
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                if time.monotonic() > deadline:
                    raise ValueError("Release download timed out")
                written += len(chunk)
                if written > MAX_DOWNLOAD or (size is not None and written > size):
                    raise ValueError("Download exceeds expected size")
                digest.update(chunk)
                target.write(chunk)
        if size is not None and written != size:
            raise ValueError("Incomplete release download")
        checksum = digest.hexdigest()
        authoritative = asset.get("digest")
        if authoritative:
            if authoritative != "sha256:" + checksum:
                raise ValueError("GitHub asset checksum mismatch")
        validate_package(temporary, name, version, expected_package_name=expected_package_name)
        if expected_root:
            repack_for_installed_folder(
                temporary, name, version, expected_root, expected_package_name
            )
            digest = hashlib.sha256()
            with open(temporary, "rb") as staged:
                for chunk in iter(lambda: staged.read(1024 * 1024), b""):
                    digest.update(chunk)
            checksum = digest.hexdigest()
        # Loader currently slices file:// instead of URL-decoding it. Runtime path
        # spaces are valid on disk and must remain literal for that implementation.
        return {
            "artifact": "file://" + str(Path(temporary).resolve()),
            "name": name,
            "version": version,
            "hash": checksum,
        }
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
