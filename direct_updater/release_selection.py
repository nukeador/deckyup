"""Manual selections are bound to a server-issued catalogue and installed identity."""

from .github_releases import compatible_releases
from .versions import Version


def release_option(plugin, release):
    option = {
        "release_id": release["id"],
        "tag": release["tag_name"],
        "version": None,
        "prerelease": bool(release.get("prerelease")),
        "installed": False,
        "downgrade": False,
        "installable": False,
        "asset_id": None,
        "reason": None,
        "release_notes": {
            key: release.get(key) for key in ("notes", "notes_truncated", "release_url")
        },
    }
    try:
        selected = Version(release["tag_name"])
        option.update(version=selected.text, prerelease=option["prerelease"] or bool(selected.pre))
    except ValueError:
        return {**option, "reason": "Tag is not a comparable SemVer version"}
    try:
        installed = Version(plugin["version"])
    except ValueError:
        return {**option, "reason": "Installed version is not comparable"}
    option.update(installed=selected == installed, downgrade=selected < installed)
    choices, ambiguous = compatible_releases(plugin, [release], allow_prerelease=True)
    if ambiguous:
        return {**option, "reason": "Multiple compatible ZIPs; cannot choose safely"}
    if not choices:
        return {**option, "reason": "No compatible plugin ZIP"}
    option["asset_id"] = choices[0][2]["id"]
    if option["installed"]:
        return {**option, "reason": "Installed version"}
    return {**option, "installable": True}


def identity(plugin):
    return tuple(plugin.get(key) for key in ("id", "name", "package_name", "version", "source"))
