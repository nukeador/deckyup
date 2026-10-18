"""Explicit repository search and selected-project validation, using existing transports."""

import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from .github_releases import GitHubError, compatible_releases
from .github_web import PublicGitHub
from .installed_plugins import repository
from .package_validation import stage_download, validate_package
from .versions import Version

LOG = logging.getLogger(__name__)


def query_identity(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 160:
        raise ValueError("Enter a plugin name or GitHub repository.")
    value = " ".join(value.strip().split())
    if "/" in value or ":" in value:
        if "://" in value:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or parsed.netloc.lower() != "github.com"
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Enter a valid GitHub repository URL.")
            value = parsed.path.strip("/")
        repo = repository(value)
        if not repo or value.strip("/").count("/") != 1:
            raise ValueError("Enter a valid GitHub repository.")
        return repo.lower(), True
    if not re.fullmatch(r"[\w .-]+", value):
        raise ValueError("Enter a plugin name or GitHub repository.")
    return value.lower(), False


def metadata(item):
    if not isinstance(item, dict):
        return None
    repo = repository(item.get("full_name"))
    if not repo:
        return None
    owner, name = repo.split("/")
    stars = item.get("stargazers_count", 0)
    return {
        "repository": repo,
        "name": name,
        "owner": owner,
        "stars": stars
        if isinstance(stars, int) and not isinstance(stars, bool) and stars >= 0
        else 0,
        "description": str(item.get("description") or "")[:300],
        "fork": item.get("fork") is True,
        "archived": item.get("archived") is True,
        "disabled": item.get("disabled") is True,
    }


def ranked(items, query):
    def compact(value):
        return re.sub(r"[^a-z0-9]", "", value.lower())

    term = compact(query)
    result = []
    for item in items:
        row = metadata(item)
        if not row:
            continue
        name = compact(row["name"])
        tier = 0 if name == term else 1 if term and term in name else 2
        if tier == 2 and not all(word in row["description"].lower() for word in query.split()):
            continue
        result.append((tier, row))
    return [
        row
        for _, row in sorted(
            result, key=lambda pair: (pair[0], -pair[1]["stars"], pair[1]["repository"].lower())
        )
    ]


class Finder:
    def __init__(self, updater):
        self.updater = updater
        self.lock = threading.RLock()
        self.known = {}
        self.selections = {}
        self.pending = {}

    def search(self, query, page=1):
        value, direct = query_identity(query)
        if type(page) is not int or not 1 <= page <= 40 or (direct and page != 1):
            raise ValueError("Invalid search page.")
        endpoint = (
            "/repos/" + value
            if direct
            else "/search/repositories?q="
            + quote(value + " in:name,description fork:true")
            + f"&sort=stars&order=desc&per_page=25&page={page}"
        )
        error = None
        try:
            data = self.updater.github.get(endpoint, ttl=21600, negative_ttl=1200, bounded=True)
        except GitHubError as failure:
            LOG.debug("Find search unavailable: %s", failure)
            cached = self.updater.state.get("cache", endpoint) or {}
            data = cached.get("data")
            error = (
                "GitHub search limit reached. Try again later."
                if "limit" in str(failure).lower()
                else "Could not reach GitHub."
            )
            if data is None:
                return {"results": [], "next_page": None, "direct": direct, "error": error}
        if direct:
            row = metadata(data)
            if not row:
                raise ValueError("Repository unavailable.")
            rows, more = [row], False
        else:
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError("Could not read GitHub search results.")
            rows = ranked(data["items"][:25], value)
            count = data.get("total_count", 1000)
            if type(count) is not int or count < 0:
                raise ValueError("Could not read GitHub search results.")
            more = len(data["items"]) >= 25 and page * 25 < min(count, 1000)
        with self.lock:
            for row in rows:
                self.known[row["repository"].lower()] = row
            while len(self.known) > 1000:
                del self.known[next(iter(self.known))]
        return {
            "results": rows,
            "next_page": page + 1 if more else None,
            "direct": direct,
            "error": error,
        }

    def _project(self, repo):
        public = PublicGitHub(self.updater.state)
        matches = []
        for prefix in ("", "plugin/"):
            try:
                manifest = public.manifest(repo, prefix + "plugin.json")
            except GitHubError as error:
                if "not found" not in str(error):
                    raise
                continue
            name = manifest.get("name")
            if not isinstance(name, str) or not name.strip() or len(name) > 160:
                continue
            try:
                package = public.manifest(repo, prefix + "package.json")
            except GitHubError as error:
                if "not found" not in str(error):
                    raise
                package = {}
            package_name = package.get("name", "")
            if not isinstance(package_name, str):
                raise ValueError("Invalid package identity.")
            matches.append({"name": name, "package_name": package_name})
        if len(matches) != 1:
            raise ValueError("No compatible Decky release found.")
        return matches[0]

    def _selection(self, repo):
        row = self.known.get(repo.lower())
        if not row:
            raise ValueError("Search for this repository first.")
        if row["disabled"] or row["archived"]:
            raise ValueError("Repository is archived or disabled.")
        project = self._project(row["repository"])
        releases = self.updater.github.releases(row["repository"], plugins=[project])
        choices, ambiguous = compatible_releases(project, releases)
        if not choices or ambiguous:
            raise ValueError("No compatible Decky release found.")
        version, release, asset = choices[0]
        if release.get("repository", repo).lower() != repo.lower():
            raise ValueError("Repository changed; search again.")
        installed = [
            p
            for p in self.updater.list_plugins()
            if p["name"] == project["name"]
            or (project["package_name"] and p["package_name"] == project["package_name"])
        ]
        status, plugin = "install", None
        if installed:
            if len(installed) != 1:
                raise ValueError("Conflicting installed plugin identity.")
            plugin = installed[0]
            if (
                not plugin["valid_identity"]
                or plugin["name"] != project["name"]
                or (project["package_name"] and plugin["package_name"] != project["package_name"])
            ):
                raise ValueError("Conflicting installed plugin identity.")
            if not plugin.get("source") or plugin["source"].lower() != repo.lower():
                raise ValueError("Already installed from another or unconfirmed source.")
            try:
                status = "update" if version > Version(plugin["version"]) else "current"
            except (ValueError, TypeError):
                status = "version_unavailable"
        return {
            "project": project,
            "version": version.text,
            "release": release,
            "asset": asset,
            "status": status,
            "plugin_id": plugin["id"] if plugin else None,
            "installed_version": plugin["version"] if plugin else None,
        }

    def details(self, repo):
        if not isinstance(repo, str) or repo.lower() not in self.known:
            raise ValueError("Search for this repository first.")
        with self.lock:
            row = self.known[repo.lower()]
            try:
                selection = self._selection(row["repository"])
            except (ValueError, OSError) as error:
                LOG.debug("Find compatibility unavailable: %s", error)
                return {
                    **row,
                    "status": "unavailable",
                    "error": str(error)
                    if str(error)
                    in {
                        "No compatible Decky release found.",
                        "Repository is archived or disabled.",
                        "Already installed from another or unconfirmed source.",
                        "Conflicting installed plugin identity.",
                        "Repository changed; search again.",
                    }
                    else "Could not check compatibility. Try again.",
                }
            token = os.urandom(24).hex()
            self.selections[token] = {
                "repository": row["repository"],
                "time": time.time(),
                "selection": selection,
            }
            while len(self.selections) > 40:
                del self.selections[next(iter(self.selections))]
            return {
                **row,
                "token": token,
                "status": selection["status"],
                "version": selection["version"],
                "installed_version": selection["installed_version"],
                "release_id": selection["release"]["id"],
                "asset_id": selection["asset"]["id"],
                "error": None,
            }

    def stage(self, token, release_id, asset_id):
        with self.lock, self.updater.operation:
            record = self.selections.get(token) if isinstance(token, str) else None
            if not record or time.time() - record["time"] > 21600:
                raise ValueError("Reopen repository details before installing.")
            selection = self._selection(record["repository"])
            if (
                selection != record["selection"]
                or selection["release"]["id"] != release_id
                or selection["asset"]["id"] != asset_id
                or selection["status"] not in {"install", "update"}
            ):
                raise ValueError("Selection changed; reopen repository details.")
            if selection["plugin_id"]:
                staged = self.updater.stage(selection["plugin_id"], release_id, asset_id)
                root = selection["plugin_id"]
            else:
                staged = stage_download(
                    selection["asset"],
                    record["repository"],
                    selection["project"]["name"],
                    selection["version"],
                    self.updater.staging,
                )
                path = Path(unquote(urlsplit(staged["artifact"]).path))
                try:
                    validated = validate_package(
                        path, selection["project"]["name"], selection["version"]
                    )
                    root = validated["root"]
                    if validated["package_name"] != selection["project"]["package_name"]:
                        raise ValueError("ZIP package identity differs from the repository.")
                    if (self.updater.plugins / root).exists() or (
                        self.updater.plugins / root
                    ).is_symlink():
                        raise ValueError("Plugin folder already exists; installation blocked.")
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                staged["install_type"] = "install"
                staged = self.updater.security.register(staged, updating=False)
            ticket = os.urandom(24).hex()
            self.pending[ticket] = {**record, "root": root, "review_token": staged["review_token"]}
            while len(self.pending) > 10:
                old = self.pending.pop(next(iter(self.pending)))
                self.updater.security.discard(old["review_token"])
            return {**staged, "install_type": selection["status"], "ticket": ticket}

    def finish(self, ticket, cancelled=False):
        with self.lock, self.updater.operation:
            record = self.pending.get(ticket) if isinstance(ticket, str) else None
            if not record:
                return {"installed": False}
            if cancelled or time.time() - record["time"] > 21600:
                self.pending.pop(ticket, None)
                self.updater.security.discard(record["review_token"])
                return {"installed": False}
            expected = record["selection"]
            if not self.updater.security.was_authorized(record["review_token"]):
                return {"installed": False}
            matches = [
                p for p in self.updater.list_plugins() if p["name"] == expected["project"]["name"]
            ]
            if len(matches) != 1:
                return {"installed": False}
            plugin = matches[0]
            if (
                not plugin["valid_identity"]
                or plugin["id"] != record["root"]
                or plugin["package_name"] != expected["project"]["package_name"]
            ):
                return {"installed": False}
            try:
                if Version(plugin["version"]) != Version(expected["version"]):
                    return {"installed": False}
            except (ValueError, TypeError):
                return {"installed": False}
            self.updater.discovery.save(plugin, record["repository"], "confirmed")
            self.pending.pop(ticket, None)
            self.updater.security.discard(record["review_token"])
            return {"installed": True}
