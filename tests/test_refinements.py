import json
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import Mock

from direct_updater.github_releases import GitHub
from direct_updater.github_web import PublicGitHub
from direct_updater.installed_plugins import repository, source_from_metadata
from direct_updater.package_validation import repack_for_installed_folder, validate_package
from direct_updater.state import State
from test_github_web import assets, page, REPO
from test_updater import Workspace, NAME, archive_bytes


class Metadata(unittest.TestCase):
    def test_github_shorthand_and_stale_template_links(self):
        self.assertEqual(
            repository("github:SteamGridDB/decky-steamgriddb"), "SteamGridDB/decky-steamgriddb"
        )
        source, note = source_from_metadata(
            {
                "repository": "https://github.com/suchmememanyskill/SDH-CssLoader",
                "homepage": "https://github.com/SteamDeckHomebrew/decky-plugin-template#readme",
            }
        )
        self.assertEqual(source, "suchmememanyskill/SDH-CssLoader")
        self.assertIsNone(note)
        self.assertIsNone(
            source_from_metadata(
                {"repository": "owner/repo", "homepage": "https://github.com/other/repo"}
            )[0]
        )

    def test_metadata_candidates_do_not_spend_search_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            github = GitHub(State(directory))
            github.get = Mock(side_effect=AssertionError("Search must not be used"))
            github.matches_manifest = Mock(return_value=True)
            github.releases = Mock(return_value=[])
            result = github.search({"name": "CSS Loader", "source_candidates": ["owner/CSSLoader"]})
            self.assertEqual(result[0]["repository"], "owner/CSSLoader")
            github.get.assert_not_called()


class Updates(Workspace):
    def test_confirmed_mapping_removes_obsolete_conflict_warning(self):
        folder = self.install()
        metadata = json.loads((folder / "package.json").read_text())
        metadata["homepage"] = "https://github.com/other/repo"
        (folder / "package.json").write_text(json.dumps(metadata))
        updater = self.updater()
        self.assertIsNotNone(updater.list_plugins()[0]["source_note"])
        updater.discovery.save(updater.list_plugins()[0], "confirmed/repo", "confirmed")
        self.assertIsNone(updater.list_plugins()[0]["source_note"])

    def test_progress_arrives_before_slow_repository_finishes(self):
        self.install("a", NAME, repo="owner/slow")
        self.install("b", "Another Plugin", repo="owner/fast")
        updater = self.updater()
        started = threading.Event()
        release = threading.Event()
        order = []

        def releases(repo, refresh=False, plugins=None):
            if repo.endswith("/slow"):
                started.set()
                if not release.wait(3):
                    raise AssertionError("Sequential lookup blocked progress")
            else:
                if not started.wait(3):
                    raise AssertionError("Slow lookup did not start")
            return []

        updater.github.releases = releases

        def progress(plugin):
            order.append(plugin["id"])
            if plugin["id"] == "b":
                release.set()

        updater.check(on_result=progress)
        self.assertEqual(order, ["b", "a"])

    def test_repack_only_changes_top_level_folder_after_identity_validation(self):
        archive = self.root / "update.zip"
        package = json.dumps(
            {
                "version": "0.1.1",
                "remote_binary": [
                    {"name": "binary", "url": "https://example.org/binary", "sha256hash": "a" * 64}
                ],
            }
        )
        archive.write_bytes(archive_bytes(extra={"plugin/package.json": package}))
        with zipfile.ZipFile(archive) as original:
            original_frontend = original.read("plugin/dist/index.js")
        repack_for_installed_folder(archive, NAME, "0.1.1", "installed-folder")
        self.assertEqual(
            validate_package(archive, NAME, "0.1.1", "installed-folder")["root"], "installed-folder"
        )
        with zipfile.ZipFile(archive) as packaged:
            self.assertEqual(packaged.read("installed-folder/dist/index.js"), original_frontend)
            self.assertEqual(packaged.read("installed-folder/package.json").decode(), package)
        with self.assertRaises(ValueError):
            repack_for_installed_folder(archive, "Wrong identity", "0.1.1", "other")
        with self.assertRaises(ValueError):
            repack_for_installed_folder(archive, NAME, "0.1.1", "../other")


class ReleaseCache(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = PublicGitHub(State(self.temporary.name))

    def test_matching_latest_release_stops_older_asset_requests_and_caches_parsed_results(self):
        self.client.text = Mock(
            side_effect=[page(("v1.2.3", "v1.2.2")), assets().replace("Plugin.zip", "Example.zip")]
        )
        plugin = {"name": "Example", "package_name": "example"}
        first = self.client.releases(REPO, plugins=[plugin])
        second = self.client.releases(REPO, True, plugins=[plugin])
        self.assertEqual(first, second)
        self.assertEqual(self.client.text.call_count, 2)
        self.assertNotIn(True, self.client.text.call_args.args[1:])

    def test_official_repository_redirect_is_used_for_asset_metadata(self):
        canonical = "newowner/plugin"
        url = "https://github.com/owner/plugin/releases?q=prerelease%3Afalse%20draft%3Afalse"
        self.client.state.put(
            "cache",
            url,
            {"time": 0, "data": "", "url": "https://github.com/" + canonical + "/releases?q=test"},
        )
        self.client.text = Mock(
            side_effect=[
                page().replace("owner/plugin", canonical),
                assets().replace("owner/plugin", canonical),
            ]
        )
        result = self.client.releases(REPO, plugins=[{"name": "Plugin"}])
        self.assertEqual(result[0]["repository"], canonical)
        self.assertIn(
            "/newowner/plugin/releases/expanded_assets/", self.client.text.call_args.args[0]
        )
