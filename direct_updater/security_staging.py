"""Bind reviews to staged bytes and the read-only installation snapshot."""

import hashlib
import os
import time
from pathlib import Path

from .installed_plugins import installed_plugins
from .capabilities import scan_installed, with_manifest
from .security import ACK_REQUIRED, CHANGED_SECURITY, assess_security


class SecurityStaging:
    def __init__(self, plugins, staging, state=None):
        self.plugins = Path(plugins)
        self.staging = Path(staging)
        self.pending = {}
        self.state = state

    def _installed(self, root, name, package_name, updating):
        inventory = installed_plugins(self.plugins)
        matches = [
            p
            for p in inventory
            if p["id"] == root
            or p["name"] == name
            or (package_name and p["package_name"] == package_name)
        ]
        if not updating:
            if matches or (self.plugins / root).exists() or (self.plugins / root).is_symlink():
                raise ValueError(CHANGED_SECURITY)
            return None
        if (
            len(matches) != 1
            or matches[0]["id"] != root
            or matches[0]["name"] != name
            or matches[0]["package_name"] != package_name
        ):
            raise ValueError(CHANGED_SECURITY)
        plugin = matches[0]
        if plugin["security"] is not None:
            plugin["security"]["capabilities"] = with_manifest(
                scan_installed(self.plugins / root), plugin["security"]
            )
        return {
            key: plugin.get(key)
            for key in (
                "id",
                "name",
                "package_name",
                "version",
                "source",
                "security",
                "valid_identity",
            )
        }

    def register(self, staged, updating):
        path = Path(staged["artifact"][7:])
        if (
            path.parent.resolve() != self.staging.resolve()
            or not path.name.startswith("update-")
            or path.suffix != ".zip"
        ):
            raise ValueError(CHANGED_SECURITY)
        try:
            previous = self._installed(
                staged["root"], staged["name"], staged["package_name"], updating
            )
            assessment = assess_security(
                staged["security_facts"], previous["security"] if previous else None, updating
            )
            if self.state and staged["security_facts"].get("capabilities"):
                self.state.put(
                    "capabilities",
                    staged["hash"],
                    {
                        "identity": [
                            staged["root"],
                            staged["name"],
                            staged["package_name"],
                            staged["version"],
                        ],
                        "analysis": staged["security_facts"]["capabilities"],
                    },
                    max_entries=32,
                )
            token = os.urandom(24).hex()
            # Internal URLs are never sent to the frontend.
            public = {
                key: value
                for key, value in staged.items()
                if key not in {"security_facts", "root", "package_name"}
            }
            public.update(
                security=assessment,
                review_token=token,
                previous_version=previous["version"] if previous else None,
            )
            self.pending[token] = {
                "staged": public,
                "path": path,
                "root": staged["root"],
                "package_name": staged["package_name"],
                "previous": previous,
                "updating": updating,
                "time": time.time(),
                "used": False,
                "facts": staged["security_facts"],
            }
            for old in list(self.pending):
                if len(self.pending) <= 32:
                    break
                self.discard(old)
            return public
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def preview(self, plugin, facts):
        # Only a still-present, byte-identical staged ZIP may describe a candidate.
        for record in reversed(list(self.pending.values())):
            previous = record["previous"]
            if (
                not previous
                or record["root"] != plugin["id"]
                or previous["version"] != plugin["version"]
                or previous["security"] != facts
            ):
                continue
            try:
                if record["path"].is_symlink() or not 0 <= time.time() - record["time"] <= 30 * 60:
                    continue
                digest = hashlib.sha256()
                with record["path"].open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() == record["staged"]["hash"]:
                    return {
                        "version": record["staged"]["version"],
                        "hash": digest.hexdigest(),
                        "assessment": record["staged"]["security"],
                    }
            except OSError:
                continue
        return None

    def discard(self, token):
        record = self.pending.pop(token, None) if isinstance(token, str) else None
        if record:
            record["path"].unlink(missing_ok=True)
        return True

    def was_authorized(self, token):
        record = self.pending.get(token)
        return bool(record and record["used"])

    def authorize(self, token, acknowledged=False):
        record = self.pending.get(token) if isinstance(token, str) else None
        if not record or record["used"]:
            raise ValueError(CHANGED_SECURITY)
        staged, path = record["staged"], record["path"]
        try:
            if (
                not 0 <= time.time() - record["time"] <= 30 * 60
                or path.is_symlink()
                or path.parent.resolve() != self.staging.resolve()
            ):
                raise ValueError(CHANGED_SECURITY)
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != staged["hash"]:
                raise ValueError(CHANGED_SECURITY)
            current = self._installed(
                record["root"], staged["name"], record["package_name"], record["updating"]
            )
            if current != record["previous"]:
                raise ValueError(CHANGED_SECURITY)
        except (OSError, ValueError) as error:
            self.discard(token)
            raise ValueError(CHANGED_SECURITY) from error
        if staged["security"]["requires_acknowledgment"] and acknowledged is not True:
            raise ValueError(ACK_REQUIRED)
        record["used"] = True
        return {**staged, "security_authorized": True}
