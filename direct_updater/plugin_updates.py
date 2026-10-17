"""Generic update pipeline; the updater itself receives no special treatment."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .github_releases import GitHub, compatible_releases
from .installed_plugins import installed_plugins
from .package_validation import stage_download
from .state import State
from .versions import Version
from .release_selection import identity, release_option
from .source_discovery import SourceDiscovery
from .find_plugins import Finder


class Updater:
    def __init__(self, plugins, settings, runtime):
        self.plugins = Path(plugins)
        self.state = State(settings)
        self.github = GitHub(self.state)
        self.staging = Path(runtime) / "staged"
        self.operation = threading.RLock()
        self.discovery = SourceDiscovery(self.state, self.github)
        self.catalogues = {}
        self.finder = Finder(self)

    def list_plugins(self):
        result = installed_plugins(self.plugins)
        names = [plugin["name"] for plugin in result]
        for plugin in result:
            self.discovery.decorate(plugin, unique=names.count(plugin["name"]) == 1)
        return result

    def plugin(self, identifier):
        matches = [item for item in self.list_plugins() if item["id"] == identifier]
        if len(matches) != 1 or not matches[0]["valid_identity"]:
            raise ValueError("Installed plugin identity unavailable")
        if sum(item["name"] == matches[0]["name"] for item in self.list_plugins()) != 1:
            raise ValueError("Duplicate installed plugin identity")
        return matches[0]

    def check(self, refresh=False, on_result=None):
        with self.operation:
            results = self.list_plugins()
            self.discovery.github = self.github
            # Check confident cached/local matches before slower manifest lookups
            # and the small automatic search budget for unresolved plugins.
            self.discovery.link(results, lightweight=True)
            checked = self._check_sources(results, refresh, on_result)
            self.discovery.link(results)
            self._check_sources(
                [plugin for plugin in results if plugin["id"] not in checked], refresh, on_result
            )
            self.discovery.suggest(results, on_result)
            return results

    def _check_sources(self, plugins, refresh, on_result):
        groups = {}
        for plugin in plugins:
            if plugin["source"]:
                groups.setdefault(plugin["source"].lower(), []).append(plugin)
        with ThreadPoolExecutor(max_workers=3) as pool:
            pending = {
                pool.submit(self.github.releases, group[0]["source"], refresh, plugins=group): group
                for group in groups.values()
            }
            for future in as_completed(pending):
                group = pending[future]
                try:
                    releases = future.result()
                    for plugin in group:
                        plugin.update(self.resolve(plugin, releases))
                except (ValueError, OSError, ImportError) as error:
                    for plugin in group:
                        plugin.update(status="error", error=str(error))
                if on_result:
                    for plugin in group:
                        on_result(dict(plugin))
        return {plugin["id"] for group in groups.values() for plugin in group}

    def resolve(self, plugin, releases):
        if not releases:
            return {"status": "no_release"}
        try:
            installed = Version(plugin["version"])
        except ValueError:
            return {"status": "version_unavailable"}
        choices, ambiguous = compatible_releases(plugin, releases)
        if not choices:
            return {"status": "ambiguous" if ambiguous else "no_compatible_release"}
        version, release, asset = choices[0]
        return {
            "status": "update" if version > installed else "current",
            "latest": version.text,
            "release_id": release["id"],
            "asset_id": asset["id"],
            "source": release.get("repository", plugin.get("source")),
        }

    def search(self, identifier):
        with self.operation:
            self.discovery.github = self.github
            return self.discovery.search(self.plugin(identifier), force=True)

    def verify_source(self, identifier, value):
        with self.operation:
            self.discovery.github = self.github
            return self.discovery.verify(self.plugin(identifier), value)

    def confirm(self, identifier, source):
        with self.operation:
            self.discovery.confirm(self.plugin(identifier), source)
            self.catalogues.pop(identifier, None)
            return True

    def list_releases(self, identifier, cursor=None):
        with self.operation:
            plugin = self.plugin(identifier)
            if not plugin["source"]:
                raise ValueError("No confirmed GitHub source")
            catalogue = self.catalogues.get(identifier)
            if cursor is None:
                catalogue = {"identity": identity(plugin), "cursors": {}, "selections": {}}
                self.catalogues[identifier] = catalogue
                after = None
            else:
                if (
                    not isinstance(cursor, str)
                    or not catalogue
                    or catalogue["identity"] != identity(plugin)
                    or cursor not in catalogue["cursors"]
                ):
                    raise ValueError("Release list changed; reopen the version selector")
                after = catalogue["cursors"][cursor]
            page = self.github.release_page(plugin["source"], after)
            options = []
            for release in page["releases"]:
                option = release_option(plugin, release)
                options.append(option)
                catalogue["selections"][release["id"]] = {"after": after, "release": release}
            next_cursor = None
            if page["next"] and page["next"] != after:
                next_cursor = os.urandom(24).hex()
                catalogue["cursors"][next_cursor] = page["next"]
            return {
                "releases": options,
                "next_cursor": next_cursor,
                "installed_version": plugin["version"],
            }

    def stage_release(self, identifier, release_id, asset_id, confirm_downgrade=False):
        with self.operation:
            plugin = self.plugin(identifier)
            catalogue = self.catalogues.get(identifier)
            if not isinstance(release_id, (str, int)) or not isinstance(asset_id, (str, int)):
                raise ValueError("Invalid release selection")
            if not catalogue or catalogue["identity"] != identity(plugin):
                raise ValueError("Plugin or source changed; reopen the version selector")
            selection = catalogue["selections"].get(release_id)
            if not selection:
                raise ValueError("Choose a release from this plugin's version selector")
            page = self.github.release_page(plugin["source"], selection["after"], refresh=True)
            matches = [item for item in page["releases"] if item["id"] == release_id]
            if len(matches) != 1 or matches[0] != selection["release"]:
                raise ValueError("Release metadata changed; reopen the version selector")
            release = matches[0]
            option = release_option(plugin, release)
            if not option["installable"] or option["asset_id"] != asset_id:
                raise ValueError(option["reason"] or "Selected asset changed")
            if option["downgrade"] and confirm_downgrade is not True:
                raise ValueError("Confirm the installed and selected versions before downgrading")
            choices, _ = compatible_releases(plugin, [release], allow_prerelease=True)
            staged = stage_download(
                choices[0][2],
                release.get("repository", plugin["source"]),
                plugin["name"],
                option["version"],
                self.staging,
                plugin["id"],
                expected_package_name=plugin["package_name"],
            )
            staged["install_type"] = "downgrade" if option["downgrade"] else "update"
            return staged

    def stage(self, identifier, release_id, asset_id):
        with self.operation:
            plugin = self.plugin(identifier)
            source = plugin["source"]
            if not source:
                raise ValueError("No confirmed GitHub source")
            # Cached GitHub metadata already binds the asset to this confirmed source.
            # The download is still checked for exact identity, version and digest.
            releases = self.github.releases(source, plugins=[plugin])
            selected = self.resolve(plugin, releases)
            if (
                selected["status"] != "update"
                or selected["release_id"] != release_id
                or selected["asset_id"] != asset_id
            ):
                raise ValueError("Selected update changed; check for updates again")
            release = next(item for item in releases if item["id"] == release_id)
            asset = next(item for item in release["assets"] if item["id"] == asset_id)
            return stage_download(
                asset,
                release.get("repository", source),
                plugin["name"],
                selected["latest"],
                self.staging,
                plugin["id"],
                expected_package_name=plugin["package_name"],
            )
