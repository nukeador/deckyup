import copy
import json
from unittest.mock import Mock, patch

from direct_updater.github_releases import compatible_releases
from direct_updater.github_web import PublicGitHub, ReleasePage
from direct_updater.release_selection import release_option
from direct_updater.state import State
from direct_updater.versions import Version
from test_github_web import REPO, assets, page
from test_updater import NAME, Workspace, archive_bytes, release


class ManualSelection(Workspace):
    def setUp(self):
        super().setUp()
        self.folder = self.install(version="1.0.0")
        self.app = self.updater()
        self.old = release("0.9.0")
        self.new = release("2.0.0-rc.1", prerelease=True)
        self.same = release("1.0.0")
        self.pages = {
            None: {"releases": [self.new, self.same], "next": "v1.0.0"},
            "v1.0.0": {"releases": [self.old], "next": None},
        }
        for item in (self.old, self.new, self.same):
            item["id"] = item["tag_name"]
        self.app.github.release_page = Mock(
            side_effect=lambda repo, after=None, refresh=False: copy.deepcopy(self.pages[after])
        )

    def test_page_cursor_is_server_issued_and_bound_to_source(self):
        first = self.app.list_releases("updater")
        self.assertEqual(len(first["releases"]), 2)
        self.assertTrue(first["releases"][0]["prerelease"])
        self.assertTrue(first["releases"][1]["installed"])
        self.assertFalse(first["releases"][1]["installable"])
        self.assertNotEqual(first["next_cursor"], "v1.0.0")
        second = self.app.list_releases("updater", first["next_cursor"])
        self.assertTrue(second["releases"][0]["downgrade"])
        self.assertIsNone(second["next_cursor"])
        with self.assertRaises(ValueError):
            self.app.list_releases("updater", "https://evil.org")
        self.app.discovery.save(self.app.plugin("updater"), "another/repository", "confirmed")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.app.list_releases("updater", first["next_cursor"])

    @patch("direct_updater.plugin_updates.stage_download", return_value={"artifact": "staged"})
    def test_explicit_downgrade_requires_consent_then_uses_generic_staging(self, stage):
        first = self.app.list_releases("updater")
        old = self.app.list_releases("updater", first["next_cursor"])["releases"][0]
        for consent in (False, "true", 1):
            with self.assertRaisesRegex(ValueError, "Confirm"):
                self.app.stage_release("updater", old["release_id"], old["asset_id"], consent)
        stage.assert_not_called()
        staged = self.app.stage_release("updater", old["release_id"], old["asset_id"], True)
        self.assertEqual(staged["install_type"], "downgrade")
        self.assertEqual(stage.call_args.args[2:4], (NAME, "0.9.0"))
        self.assertEqual(stage.call_args.args[-1], "updater")
        self.assertTrue(self.app.github.release_page.call_args.kwargs["refresh"])

    @patch("direct_updater.plugin_updates.stage_download", return_value={})
    def test_prerelease_manual_only_and_does_not_save_channel(self, stage):
        selected = self.app.list_releases("updater")["releases"][0]
        result = self.app.stage_release("updater", selected["release_id"], selected["asset_id"])
        self.assertEqual(result["install_type"], "update")
        self.assertEqual(self.app.state.get("sources", NAME), None)
        self.assertEqual(compatible_releases(self.app.plugin("updater"), [self.new]), ([], False))
        with self.assertRaises(ValueError):
            self.app.stage("updater", selected["release_id"], selected["asset_id"])

    @patch("direct_updater.plugin_updates.stage_download")
    def test_forged_ids_current_version_and_changed_metadata_are_rejected(self, stage):
        self.app.list_releases("updater")
        for release_id, asset_id in (
            ("https://evil.org", 20),
            (self.new["id"], "wrong.zip"),
            (self.same["id"], 20),
        ):
            with self.assertRaises(ValueError):
                self.app.stage_release("updater", release_id, asset_id, True)
        self.new["assets"][0]["digest"] = "sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.app.stage_release("updater", self.new["id"], 20, True)
        stage.assert_not_called()

    @patch("direct_updater.plugin_updates.stage_download")
    def test_changed_repository_or_installed_version_invalidates_consent(self, stage):
        for key, value in (
            ("repository", "other/repo"),
            ("version", "1.0.1"),
            ("name", "other-package"),
        ):
            self.app.list_releases("updater")
            metadata = json.loads((self.folder / "package.json").read_text())
            changed = {**metadata, key: value}
            (self.folder / "package.json").write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "changed"):
                self.app.stage_release("updater", self.new["id"], 20, True)
            (self.folder / "package.json").write_text(json.dumps(metadata))
        stage.assert_not_called()

    def test_ambiguous_missing_nonsemver_and_dev_beta_rc(self):
        plugin = self.app.plugin("updater")
        for version in ("2.0.0-dev.1", "2.0.0-beta.2", "2.0.0-rc.1"):
            option = release_option(plugin, release(version, prerelease=True))
            self.assertTrue(option["installable"])
            self.assertTrue(option["prerelease"])
        self.assertLess(Version("2.0.0-beta.2"), Version("2.0.0-rc.1"))
        for item in (release("nightly"), release("2.0.0", filename="source.zip")):
            self.assertFalse(release_option(plugin, item)["installable"])
        ambiguous = release("2.0.0")
        ambiguous["assets"].append(
            {**ambiguous["assets"][0], "id": 21, "name": "Decky-Direct-Updater.zip"}
        )
        self.assertIn("Multiple", release_option(plugin, ambiguous)["reason"])

    def test_manual_staging_rejects_mismatching_zip_identity_and_version(self):
        self.app.list_releases("updater")
        # Use the real generic staging path, including download and ZIP verification.
        self.new["assets"][0]["size"] = None
        self.app.list_releases("updater")
        for data, message in (
            (archive_bytes(name="Other", version="2.0.0-rc.1"), "name does not match"),
            (archive_bytes(version="2.0.0"), "version does not match"),
        ):
            response = Mock()
            response.headers = {"Content-Length": str(len(data))}
            response.geturl.return_value = self.new["assets"][0]["browser_download_url"]
            response.read.side_effect = [data, b""]
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            opener = Mock()
            opener.open.return_value = response
            with patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaisesRegex(ValueError, message):
                    self.app.stage_release("updater", self.new["id"], 20)


class WebPages(Workspace):
    def test_public_pages_include_prereleases_and_opaque_nonsemver_tags(self):
        client = PublicGitHub(State(self.root / "state"))
        html = page(("v2.0.0-rc.1", "v1.0.0", "nightly"))
        html = html.replace(
            "<include-fragment", '<span class="Label">Pre-release</span><include-fragment', 1
        )
        html += f'<a rel="next" href="/{REPO}/releases?after=v1.0.0&amp;q=draft%3Afalse">Next</a>'

        def read(url, refresh=False):
            if "expanded_assets" in url:
                tag = url.rsplit("/", 1)[-1]
                return assets(tag)
            return html

        client.text = Mock(side_effect=read)
        result = client.release_page(REPO)
        self.assertEqual(result["next"], "v1.0.0")
        self.assertTrue(result["releases"][0]["prerelease"])
        self.assertEqual(result["releases"][-1]["assets"], [])
        client.release_page(REPO, result["next"])
        self.assertIn("after=v1.0.0", client.text.call_args_list[-3].args[0])

    def test_pagination_rejects_foreign_links_and_drafts(self):
        parser = ReleasePage(REPO)
        parser.feed(
            page().replace("<include-fragment", '<span class="Label">Draft</span><include-fragment')
            + '<a rel="next" href="https://evil.org/releases?after=bad">Next</a>'
        )
        self.assertIsNone(parser.next_after)
        self.assertIn("v1.2.3", parser.drafts)

    def test_numeric_pagination_used_by_github_search_filter(self):
        client = PublicGitHub(State(self.root / "state"))
        html = (
            page()
            + f'<a class="next_page" rel="next" href="/{REPO}/releases?page=2&amp;q=draft%3Afalse">Next</a>'
        )
        client.text = Mock(
            side_effect=lambda url, refresh=False: assets() if "expanded_assets" in url else html
        )
        result = client.release_page(REPO)
        self.assertEqual(result["next"], "page:2")
        client.release_page(REPO, result["next"])
        self.assertIn("page=2", client.text.call_args_list[-2].args[0])


class GenericSelfSelection(Workspace):
    def setUp(self):
        super().setUp()
        self.folder = self.install(version="1.0.0")
        self.app = self.updater()
        self.new = release("2.0.0-rc.1", prerelease=True)
        self.app.github.release_page = Mock(
            side_effect=lambda *args, **kwargs: {
                "releases": [copy.deepcopy(self.new)],
                "next": None,
            }
        )

    def test_self_update_manual_selection_uses_validated_generic_pipeline(self):
        import hashlib
        import zipfile
        from pathlib import Path

        data = archive_bytes(version="2.0.0-rc.1")
        self.new["assets"][0]["size"] = len(data)
        self.new["assets"][0]["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
        self.app.list_releases("updater")
        before = (self.folder / "package.json").read_bytes()
        response = Mock()
        response.headers = {"Content-Length": str(len(data))}
        response.geturl.return_value = self.new["assets"][0]["browser_download_url"]
        response.read.side_effect = [data, b""]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            staged = self.app.stage_release("updater", self.new["id"], 20)
        path = Path(staged["artifact"][7:])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), staged["hash"])
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(json.loads(archive.read("updater/plugin.json"))["name"], NAME)
            self.assertEqual(
                json.loads(archive.read("updater/package.json"))["version"], "2.0.0-rc.1"
            )
        self.assertEqual((self.folder / "package.json").read_bytes(), before)
