import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from direct_updater.github_releases import (
    GitHub,
    GitHubError,
    SafeRedirect,
    check_download_url,
    compatible_releases,
)
from direct_updater.installed_plugins import installed_plugins, repository, source_from_metadata
from direct_updater.package_validation import (
    MAX_DOWNLOAD,
    cleanup_staged,
    stage_download,
    validate_package,
)
from direct_updater.plugin_updates import Updater
from direct_updater.state import State
from direct_updater.versions import Version

NAME = "Decky Direct Updater"
REPO = "nukeador/decky-direct-updater"


def release(version="0.1.1", filename=None, **extra):
    return {
        "id": 10,
        "tag_name": "v" + version,
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "id": 20,
                "name": filename or f"Decky-Direct-Updater-v{version}.zip",
                "browser_download_url": f"https://github.com/{REPO}/releases/download/v{version}/plugin.zip",
            }
        ],
        **extra,
    }


def archive_bytes(name=NAME, version="0.1.1", extra=None, missing=None):
    stream = io.BytesIO()
    files = {
        "plugin/plugin.json": json.dumps({"name": name}),
        "plugin/package.json": json.dumps({"version": version}),
        "plugin/dist/index.js": "export default {};",
    }
    files.update(extra or {})
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in files.items():
            if path != missing:
                archive.writestr(path, data)
    return stream.getvalue()


class Workspace(unittest.TestCase):
    def staged_package(
        self, version="0.1.1", folder="updater", package="decky-direct-updater", extra=None
    ):
        directory = self.root / "data" / "staged"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "update-test.zip"
        path.write_bytes(
            archive_bytes(
                version=version,
                extra={
                    "plugin/package.json": json.dumps({"name": package, "version": version}),
                    **(extra or {}),
                },
            )
        )
        info = validate_package(path, NAME, version)
        return {
            "artifact": path.as_uri(),
            "name": NAME,
            "version": version,
            "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            "root": folder,
            "package_name": package,
            "security_facts": info["security"],
        }

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def install(self, folder="updater", name=NAME, version="0.1.0", repo=REPO):
        target = self.root / "plugins" / folder
        target.mkdir(parents=True)
        (target / "plugin.json").write_text(json.dumps({"name": name}))
        (target / "package.json").write_text(
            json.dumps({"name": "decky-direct-updater", "version": version, "repository": repo})
        )
        return target

    def updater(self):
        app = Updater(self.root / "plugins", self.root / "settings", self.root / "data")
        app.github.official_sources = Mock(return_value={})
        app.github.matches_manifest = Mock(return_value=True)
        app.github.canonical_repository = Mock(side_effect=lambda repo: repo)
        return app


class Versions(unittest.TestCase):
    def test_ordering(self):
        for newer, older in [
            ("0.3.20", "0.3.19"),
            ("0.3.10", "0.3.9"),
            ("4.5.0", "4.4.9"),
            ("1.0.0", "1.0.0-rc.1"),
            ("1.0.0-rc.10", "1.0.0-rc.2"),
            ("1.0.0-beta", "1.0.0-1"),
            ("2.0.0-dev", "1.9.9"),
        ]:
            with self.subTest(newer=newer):
                self.assertGreater(Version(newer), Version(older))
                self.assertLess(Version(older), Version(newer))

    def test_prefixes_and_builds(self):
        self.assertEqual(Version("plugin-v4.5.0"), Version("4.5.0"))
        self.assertEqual(Version("v1.2.3+build.5"), Version("1.2.3"))
        self.assertEqual(Version("v0.17"), Version("0.17.0"))
        self.assertEqual(Version("v0.17").text, "0.17.0")
        self.assertGreater(Version("v0.17"), Version("0.16.3-pre"))
        for bad in ["latest", "1", "01.2.3", "1.0.0-01", "1.0.0+.."]:
            with self.assertRaises(ValueError):
                Version(bad)


class Installed(Workspace):
    def test_versions_disabled_and_malformed(self):
        target = self.install()
        (target / "plugin.json").write_text(
            json.dumps({"name": NAME, "version": "0.0.1", "disabled": True})
        )
        broken = self.install("broken", "Broken")
        (broken / "package.json").write_text("{invalid")
        self.install(
            "decktation",
            "Decktation",
            "0.3.19",
            {"type": "git", "url": "git+https://github.com/silverfoxy/decktation.git"},
        )
        items = installed_plugins(self.root / "plugins")
        self.assertEqual(len(items), 3)
        by_name = {item["name"]: item for item in items}
        self.assertEqual(by_name[NAME]["version"], "0.1.0")
        self.assertEqual(by_name["Decktation"]["source"], "silverfoxy/decktation")
        self.assertTrue(by_name["Broken"]["metadata_error"])

    def test_missing_metadata_and_read_failure(self):
        folder = self.install()
        (folder / "package.json").unlink()
        self.assertIsNone(installed_plugins(self.root / "plugins")[0]["version"])
        with patch(
            "direct_updater.installed_plugins.read_json", side_effect=PermissionError("no access")
        ):
            self.assertFalse(installed_plugins(self.root / "plugins")[0]["valid_identity"])

    def test_symlink_directory_ignored(self):
        self.install()
        (self.root / "plugins" / "link").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(len(installed_plugins(self.root / "plugins")), 1)

    def test_sources(self):
        for value in [
            "https://github.com/a/b",
            {"url": "git+https://github.com/a/b.git"},
            "git@github.com:a/b.git",
            "https://github.com/a/b/tree/main/plugin",
        ]:
            self.assertEqual(repository(value), "a/b")
        for value in [
            "https://evil.com/a/b",
            "https://github.com.evil/a/b",
            "https://github.com/a",
            "a/..",
            "http://github.com/a/b",
        ]:
            self.assertIsNone(repository(value))
        self.assertEqual(
            source_from_metadata({"repository": "a/b", "homepage": "https://github.com/c/d"})[0],
            None,
        )
        self.assertIsNone(source_from_metadata({"homepage": "https://github.com/a/b"})[0])

    def test_confirmed_persistence_and_ambiguity(self):
        self.install(repo=None)
        updater = self.updater()
        updater.github.search = Mock(return_value=[{"repository": "a/b"}, {"repository": "c/d"}])
        self.assertEqual(len(updater.search("updater")), 2)
        self.assertIsNone(updater.list_plugins()[0]["source"])
        with self.assertRaises(ValueError):
            updater.confirm("updater", "evil/source")
        updater.confirm("updater", "a/b")
        self.assertEqual(self.updater().list_plugins()[0]["source"], "a/b")


class Releases(Workspace):
    def setUp(self):
        super().setUp()
        self.install()
        self.app = self.updater()
        self.plugin = self.app.list_plugins()[0]

    def test_new_equal_downgrade_development_and_self_update(self):
        for installed, latest, expected in [
            ("0.1.0", "0.1.1", "update"),
            ("0.1.1", "0.1.1", "current"),
            ("0.2.0-dev.1", "0.1.1", "current"),
            ("0.1.2", "0.1.1", "current"),
        ]:
            self.plugin["version"] = installed
            self.assertEqual(self.app.resolve(self.plugin, [release(latest)])["status"], expected)
        self.assertEqual(self.plugin["source"], REPO)

    def test_drafts_prereleases_wrong_missing_ambiguous(self):
        for entry in [
            release(prerelease=True),
            release(draft=True),
            release("0.2.0-rc.1"),
            release(filename="Other-Tool.zip"),
            release(assets=[]),
        ]:
            self.assertEqual(compatible_releases(self.plugin, [entry])[0], [])
        entry = release()
        entry["assets"].append({"id": 21, "name": "Decky-Direct-Updater-v0.1.1.zip"})
        self.assertEqual(self.app.resolve(self.plugin, [entry])["status"], "ambiguous")
        self.assertEqual(self.app.resolve(self.plugin, [])["status"], "no_release")

    def test_mako_multicomponent(self):
        plugin = {"name": "MAKO - Frame Generation", "package_name": "mako-plugin"}
        plugin_release = release("4.5.0", "MAKO-Decky-v4.5.0.zip", tag_name="plugin-v4.5.0")
        application = release("9.0.0", "MAKO-linux.tar.gz")
        choices, _ = compatible_releases(plugin, [application, plugin_release])
        self.assertEqual(choices[0][0], Version("4.5.0"))

    def test_invalid_version_and_offline(self):
        self.plugin["version"] = "development"
        self.assertEqual(
            self.app.resolve(self.plugin, [release()])["status"], "version_unavailable"
        )
        self.app.github.releases = Mock(side_effect=GitHubError("offline"))
        self.assertEqual(self.app.check()[0]["status"], "error")

    def test_shared_repo_deduplication(self):
        self.install("another", "Another Plugin")
        self.app.github.releases = Mock(return_value=[])
        self.assertEqual(len(self.app.check(True)), 2)
        self.assertEqual(self.app.github.releases.call_count, 1)
        self.assertEqual(self.app.github.releases.call_args.args, (REPO, True))
        self.assertEqual(len(self.app.github.releases.call_args.kwargs["plugins"]), 2)

    def test_stage_resolves_identifiers_and_generic_self_update(self):
        entry = release()
        self.app.github.releases = Mock(return_value=[entry])
        with patch(
            "direct_updater.plugin_updates.stage_download", return_value=self.staged_package()
        ) as stage:
            self.app.stage("updater", 10, 20)
            self.assertEqual(stage.call_args.args[1:4], (REPO, NAME, "0.1.1"))
            self.assertEqual(
                stage.call_args.kwargs["expected_package_name"], "decky-direct-updater"
            )
            with self.assertRaises(ValueError):
                self.app.stage("updater", 10, 999)
            with self.assertRaises(ValueError):
                self.app.stage("../not-installed", 10, 20)


class HTTP(Workspace):
    def setUp(self):
        super().setUp()
        self.client = GitHub(State(self.root))
        self.client.opener = Mock()

    def response(self, data, headers=None):
        response = Mock()
        response.read.return_value = json.dumps(data).encode()
        response.headers = headers or {}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_cache_etag_and_304(self):
        self.client.opener.open.return_value = self.response([], {"ETag": '"abc"'})
        self.assertEqual(self.client.get("/repos/a/b/releases"), [])
        self.client.get("/repos/a/b/releases")
        self.assertEqual(self.client.opener.open.call_count, 1)
        self.client.state.data["cache"]["/repos/a/b/releases"]["time"] -= 61
        self.client.opener.open.side_effect = urllib.error.HTTPError("url", 304, "", {}, None)
        self.assertEqual(self.client.get("/repos/a/b/releases", True), [])
        request = self.client.opener.open.call_args.args[0]
        self.assertEqual(request.get_header("If-none-match"), '"abc"')

    def test_timeout_rate_limit_and_errors(self):
        for error in [
            TimeoutError(),
            urllib.error.HTTPError("url", 500, "", {}, None),
            urllib.error.HTTPError("url", 429, "", {"Retry-After": "120"}, None),
        ]:
            self.client.opener.open.side_effect = error
            with self.assertRaises(GitHubError):
                self.client.get("/repos/a/b/releases", True)
        calls = self.client.opener.open.call_count
        with self.assertRaises(GitHubError):
            self.client.get("/repos/a/b/releases", True)
        self.assertEqual(calls, self.client.opener.open.call_count)

    def test_nested_manifest_search(self):
        with patch(
            "direct_updater.github_web.PublicGitHub.manifest",
            side_effect=[GitHubError("manifest not found"), {"name": "MAKO - Frame Generation"}],
        ) as manifest:
            self.assertTrue(
                self.client.matches_manifest("eugeniosegala/MAKO", "MAKO - Frame Generation")
            )
        self.assertEqual(manifest.call_args.args[1], "plugin/plugin.json")

    def test_redirect_boundary(self):
        for url in [
            "http://github.com/a",
            "https://evil.com/a",
            "https://github.com:444/a",
            "https://user@github.com/a",
        ]:
            with self.assertRaises(ValueError):
                check_download_url(url)
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(Mock(), None, 302, "", {}, "http://localhost/secret")


class Packages(Workspace):
    def validate(self, data, **kwargs):
        path = self.root / "plugin.zip"
        path.write_bytes(data)
        return validate_package(path, kwargs.get("name", NAME), kwargs.get("version", "0.1.1"))

    def test_valid(self):
        self.assertEqual(self.validate(archive_bytes())["root"], "plugin")

    def test_update_zip_must_keep_installed_package_identity(self):
        asset = release()["assets"][0]
        for package_name, accepted in (
            ("other-plugin", False),
            ("decky-direct-updater", True),
        ):
            data = archive_bytes(
                extra={
                    "plugin/package.json": json.dumps({"name": package_name, "version": "0.1.1"})
                }
            )
            asset["size"] = len(data)
            response = Mock()
            response.headers = {"Content-Length": str(len(data))}
            response.geturl.return_value = asset["browser_download_url"]
            response.read.side_effect = [data, b""]
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            opener = Mock()
            opener.open.return_value = response
            with patch("urllib.request.build_opener", return_value=opener):
                if accepted:
                    staged = stage_download(
                        asset,
                        REPO,
                        NAME,
                        "0.1.1",
                        self.root / "staged",
                        "updater",
                        expected_package_name="decky-direct-updater",
                    )
                    self.assertTrue(Path(staged["artifact"][7:]).exists())
                else:
                    with self.assertRaisesRegex(ValueError, "package identity"):
                        stage_download(
                            asset,
                            REPO,
                            NAME,
                            "0.1.1",
                            self.root / "staged",
                            "updater",
                            expected_package_name="decky-direct-updater",
                        )
                    self.assertEqual(list((self.root / "staged").glob("*.zip")), [])

    def test_invalid_identity_version_missing_corrupt_and_paths(self):
        cases = [
            b"not a zip",
            archive_bytes(name="Other"),
            archive_bytes(version="0.0.1"),
            archive_bytes(missing="plugin/plugin.json"),
            archive_bytes(extra={"plugin/../evil": "x"}),
            archive_bytes(extra={"/absolute": "x"}),
            archive_bytes(extra={"plugin/sub/plugin.json": "{}"}),
            archive_bytes(extra={"plugin\\evil": "x"}),
        ]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                self.validate(data)

    def test_links_duplicates_and_expansion(self):
        stream = io.BytesIO(archive_bytes())
        with zipfile.ZipFile(stream, "a") as archive:
            link = zipfile.ZipInfo("plugin/link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "/etc/passwd")
        with self.assertRaises(ValueError):
            self.validate(stream.getvalue())
        with (
            patch("direct_updater.package_validation.MAX_EXPANDED", 5),
            self.assertRaises(ValueError),
        ):
            self.validate(archive_bytes())
        with self.assertRaises(ValueError):
            self.validate(archive_bytes(extra={"plugin/PLUGIN.json": "{}"}))

    def test_download_hash_checksum_limits_cleanup(self):
        data = archive_bytes()
        asset = release()["assets"][0]
        asset["size"] = len(data)
        asset["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
        response = Mock()
        response.headers = {}
        response.read.side_effect = [data, b""]
        response.geturl.return_value = asset["browser_download_url"]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            staged = stage_download(asset, REPO, NAME, "0.1.1", self.root / "staged")
        self.assertEqual(staged["hash"], hashlib.sha256(data).hexdigest())
        self.assertTrue(Path(staged["artifact"][7:]).exists())
        asset["size"] = MAX_DOWNLOAD + 1
        with self.assertRaises(ValueError):
            stage_download(asset, REPO, NAME, "0.1.1", self.root)
        asset["size"] = len(data)
        asset["digest"] = "sha256:" + "0" * 64
        response.read.side_effect = [data, b""]
        with (
            patch("urllib.request.build_opener", return_value=opener),
            self.assertRaisesRegex(ValueError, "checksum"),
        ):
            stage_download(asset, REPO, NAME, "0.1.1", self.root / "bad")
        self.assertEqual(list((self.root / "bad").glob("*.zip")), [])
        path = Path(staged["artifact"][7:])
        os.utime(path, (0, 0))
        cleanup_staged(path.parent)
        self.assertFalse(path.exists())

    def test_wrong_repository_and_short_download(self):
        asset = release()["assets"][0]
        asset["size"] = 100
        with self.assertRaises(ValueError):
            stage_download(asset, "other/repo", NAME, "0.1.1", self.root)


class Regression(Workspace):
    def test_invalid_repository_and_version_metadata_does_not_hide_plugins(self):
        folder = self.install(repo="https://[invalid/")
        metadata = json.loads((folder / "package.json").read_text())
        metadata["version"] = {"invalid": True}
        (folder / "package.json").write_text(json.dumps(metadata))
        item = installed_plugins(self.root / "plugins")[0]
        self.assertIsNone(item["source"])
        self.assertIsNone(item["version"])

    def test_missing_runtime_module_is_a_per_plugin_error(self):
        self.install()
        updater = self.updater()
        updater.github.releases = Mock(side_effect=ModuleNotFoundError("Missing runtime module"))
        result = updater.check()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "error")
        self.assertIn("Missing runtime module", result[0]["error"])

    def test_invalid_state_is_preserved(self):
        (self.root / "state.json").write_text('{"sources": []}')
        with self.assertRaises(ValueError):
            State(self.root)
        self.assertEqual((self.root / "state.json").read_text(), '{"sources": []}')

    def test_newest_ambiguous_does_not_offer_older_release(self):
        self.install()
        app = self.updater()
        newest = release("0.2.0")
        newest["assets"].append({"id": 21, "name": "Decky-Direct-Updater-v0.2.0.zip"})
        self.assertEqual(
            app.resolve(app.list_plugins()[0], [newest, release()])["status"], "ambiguous"
        )

    def test_source_archives_and_non_plugin_components_are_ignored(self):
        plugin = {"name": "MAKO - Frame Generation", "package_name": "mako-plugin"}
        for name in ["MAKO-source.zip", "MAKO.zip", "MAKO-renderer.zip"]:
            self.assertEqual(compatible_releases(plugin, [release("4.5.0", name)])[0], [])

    def test_root_mismatch_is_rejected_but_remote_binaries_pass_to_loader(self):
        path = self.root / "plugin.zip"
        path.write_bytes(archive_bytes())
        with self.assertRaisesRegex(ValueError, "folder differs"):
            validate_package(path, NAME, "0.1.1", "other-plugin")
        path.write_bytes(
            archive_bytes(
                extra={
                    "plugin/package.json": json.dumps(
                        {
                            "version": "0.1.1",
                            "remote_binary": [
                                {"name": "binary", "url": "https://example.org/binary"}
                            ],
                        }
                    )
                }
            )
        )
        self.assertEqual(validate_package(path, NAME, "0.1.1")["version"], "0.1.1")

    def test_parent_file_conflict_is_rejected(self):
        path = self.root / "plugin.zip"
        path.write_bytes(
            archive_bytes(extra={"plugin/conflict": "file", "plugin/conflict/child": "child"})
        )
        with self.assertRaisesRegex(ValueError, "parent directory"):
            validate_package(path, NAME, "0.1.1")

    def test_streaming_size_and_incomplete_download_cleanup(self):
        for chunks, size in [([b"longer-than-declared", b""], 1), ([b"short", b""], 100)]:
            asset = release()["assets"][0]
            asset["size"] = size
            response = Mock()
            response.headers = {}
            response.read.side_effect = chunks
            response.geturl.return_value = asset["browser_download_url"]
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            opener = Mock()
            opener.open.return_value = response
            with (
                patch("urllib.request.build_opener", return_value=opener),
                self.assertRaises(ValueError),
            ):
                stage_download(asset, REPO, NAME, "0.1.1", self.root / "staged")
            self.assertEqual(list((self.root / "staged").glob("*.zip")), [])

    def test_disk_space_failure_precedes_download(self):
        asset = release()["assets"][0]
        asset["size"] = 100
        with (
            patch("shutil.disk_usage", return_value=Mock(free=1)),
            self.assertRaisesRegex(ValueError, "disk space"),
        ):
            stage_download(asset, REPO, NAME, "0.1.1", self.root)


if __name__ == "__main__":
    unittest.main()
