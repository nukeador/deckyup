"""Read only the upstream submodule index, never clone the plugin database."""

import re

from .installed_plugins import is_template, repository

URL = "https://raw.githubusercontent.com/SteamDeckHomebrew/decky-plugin-database/main/.gitmodules"
TTL = 24 * 60 * 60


def parse_gitmodules(text):
    result = {}
    current = {}

    def store():
        path = current.get("path", "")
        source = repository(current.get("url"))
        if re.fullmatch(r"plugins/[^/\\\s]+", path) and source and not is_template(source):
            folder = path.split("/")[1]
            if folder.startswith("."):
                return
            repos = result.setdefault(folder.lower(), [])
            if source.lower() not in {repo.lower() for repo in repos}:
                repos.append(source)

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            store()
            current = {}
        elif "=" in line:
            key, value = line.split("=", 1)
            if key.strip() in {"path", "url"}:
                current[key.strip()] = value.strip().strip('"')
    store()
    if not result:
        raise ValueError("Cannot read official Decky repository index")
    return result
