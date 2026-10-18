"""Read-only inspection of Decky's managed plugin directory."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .security import public_facts, security_facts

_REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+$")


def repository(value):
    if isinstance(value, dict):
        value = value.get("url")
    if not isinstance(value, str):
        return None
    value = value.strip().removeprefix("git+").removeprefix("github:")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    if "://" in value:
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        host = parsed.netloc.lower()
        allowed = (parsed.scheme in {"https", "git"} and host == "github.com") or (
            parsed.scheme == "ssh" and host == "git@github.com"
        )
        if not allowed:
            return None
        value = parsed.path.strip("/")
        parts = value.split("/")
        if len(parts) > 2:
            if parts[2] not in ("issues", "tree"):
                return None
            value = "/".join(parts[:2])
    value = value.removesuffix(".git").rstrip("/")
    if not _REPO.fullmatch(value) or value.split("/")[1] in (".", ".."):
        return None
    return value


def is_template(source):
    return bool(
        source and source.lower().split("/")[-1] in {"decky-plugin-template", "plugin-template"}
    )


def metadata_sources(*manifests):
    primary, secondary = [], []
    for manifest in manifests:
        bugs = manifest.get("bugs", {})
        primary.append(repository(manifest.get("repository")))
        secondary.extend(
            (
                repository(manifest.get("homepage")),
                repository(bugs.get("url") if isinstance(bugs, dict) else bugs),
            )
        )

    def unique(values):
        return list(
            {value.lower(): value for value in values if value and not is_template(value)}.values()
        )

    return unique(primary), unique(secondary)


def source_from_metadata(package, manifest=None):
    primary, secondary = metadata_sources(package, manifest or {})
    evidence = {item.lower() for item in primary + secondary}
    if len(evidence) > 1:
        return None, "Conflicting GitHub metadata; confirm a source"
    if primary:
        return primary[0], None
    return None, ("Confirm GitHub source from metadata" if secondary else None)


def discovery_identity(plugin):
    return [plugin["id"], plugin["name"], plugin.get("package_name", "")]


def source_matches_identity(plugin, source):
    # An explicit repository plus an exact local project identifier is stronger
    # than a display-name search. Other metadata needs remote manifest checking.
    def key(value):
        return "".join(
            part
            for part in re.findall(r"[a-z0-9]+", str(value).lower())
            if part not in {"decky", "plugin"}
        )

    slug = key(source.split("/")[-1])
    return len(slug) >= 3 and slug in {key(plugin["id"]), key(plugin.get("package_name", ""))}


def read_json(path):
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Unsafe or oversized metadata")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be an object")
    return data


def installed_plugins(root):
    result = []
    for folder in sorted(Path(root).iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            continue
        # A Decky manifest distinguishes plugins from ordinary neighbouring folders.
        # Keep malformed/unreadable manifests visible rather than hiding broken plugins.
        try:
            (folder / "plugin.json").lstat()
        except FileNotFoundError:
            continue
        except OSError:
            pass
        errors = []
        metadata = []
        for name in ("plugin.json", "package.json"):
            try:
                metadata.append(read_json(folder / name))
            except (OSError, ValueError) as error:
                metadata.append({})
                errors.append(f"{name}: {error}")
        manifest, package = metadata
        security = None
        if not errors:
            try:
                backend = folder / "main.py"
                if backend.is_symlink():
                    raise ValueError("Unknown backend")
                security = public_facts(security_facts(manifest, package, backend.is_file()))
            except (OSError, ValueError):
                pass
        name = manifest.get("name")
        if not isinstance(name, str) or not name:
            name = folder.name
            errors.append("Decky identity unavailable; installation disabled")
        source, conflict = source_from_metadata(package, manifest)
        result.append(
            {
                "id": folder.name,
                "security": security,
                "name": name,
                "version": (
                    package.get("version") if "version" in package else manifest.get("version")
                )
                if isinstance(package.get("version", manifest.get("version")), str)
                else None,
                "package_name": package.get("name", "")
                if isinstance(package.get("name", ""), str)
                else "",
                "source": source,
                "source_note": conflict,
                "source_candidates": list(
                    dict.fromkeys(sum(metadata_sources(package, manifest), []))
                ),
                "metadata_primary": metadata_sources(package, manifest)[0],
                "author": manifest.get("author", package.get("author", "")),
                "discovery_fingerprint": hashlib.sha256(
                    json.dumps(
                        {
                            "identity": [folder.name, name, package.get("name", "")],
                            "metadata": [
                                {
                                    key: data.get(key)
                                    for key in ("repository", "homepage", "bugs", "author")
                                }
                                for data in (package, manifest)
                            ],
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
                "metadata_error": "; ".join(errors) or None,
                "valid_identity": manifest.get("name") == name,
            }
        )
    return result
