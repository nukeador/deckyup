"""Request budgets and installation boundaries use mocked GitHub, never live requests."""

import json
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from direct_updater.find_plugins import query_identity, ranked
from direct_updater.github_releases import GitHubError
from direct_updater.versions import Version
from test_updater import Workspace, NAME, REPO, release, archive_bytes


def item(repo=REPO, stars=42, **extra):
    return {
        "full_name": repo,
        "stargazers_count": stars,
        "description": "Decky Direct Updater",
        **extra,
    }


class FindPlugins(Workspace):
    def setUp(self):
        super().setUp()
        (self.root / "plugins").mkdir()
        self.app = self.updater()
        self.finder = self.app.finder
        self.opener = self.app.github.opener = Mock()
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.headers = {"ETag": '"find"'}
        self.opener.open.return_value = self.response
        self.response.read.return_value = json.dumps({"items": [item()], "total_count": 1}).encode()

    def authorize(self):
        self.finder.search("direct updater")

    def project(self, nested=False, package="decky-direct-updater"):
        def manifest(repo, path, **kwargs):
            prefix = "plugin/" if nested else ""
            if path == prefix + "plugin.json":
                return {"name": NAME}
            if path == prefix + "package.json":
                return {"name": package}
            raise GitHubError("GitHub repository or manifest not found")

        return patch("direct_updater.find_plugins.PublicGitHub.manifest", side_effect=manifest)

    def test_unused_finder_adds_zero_requests(self):
        self.app.list_plugins()
        self.opener.open.assert_not_called()

    def test_search_one_request_with_metadata_and_cached_repeat(self):
        result = self.finder.search("  Direct   Updater ")
        self.assertEqual(result["results"][0]["stars"], 42)
        self.assertEqual(result["results"][0]["owner"], "nukeador")
        self.finder.search("direct updater")
        self.assertEqual(self.opener.open.call_count, 1)
        url = self.opener.open.call_args.args[0].full_url
        self.assertIn("fork%3Atrue", url)
        self.assertIn("per_page=25", url)
        self.assertIn("sort=stars", url)

    def test_concurrent_identical_search_is_single_flight(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _: self.finder.search("direct updater"), range(6)))
        self.assertEqual(self.opener.open.call_count, 1)

    def test_direct_lookup_bypasses_search_and_reuses_cache(self):
        self.response.read.return_value = json.dumps(item()).encode()
        for query in (REPO, "https://github.com/" + REPO):
            result = self.finder.search(query)
            self.assertTrue(result["direct"])
        self.assertEqual(self.opener.open.call_count, 1)
        self.assertIn("/repos/" + REPO, self.opener.open.call_args.args[0].full_url)

    def test_invalid_inputs_and_pages_do_not_request(self):
        for query in (
            "https://github.com.evil/x/y",
            "http://github.com/x/y",
            "https://github.com/a/b?x=1",
            "a/b/c",
            "",
            "x" * 161,
            "x user:someone",
        ):
            with self.assertRaises(ValueError):
                self.finder.search(query)
        for page in (0, 41, True, "1"):
            with self.assertRaises(ValueError):
                self.finder.search("foo", page)
        self.opener.open.assert_not_called()

    def test_relevance_stars_forks_and_deterministic_ties(self):
        rows = ranked(
            [
                item("a/MAKO", 10),
                item("b/MAKO", 20, fork=True),
                item("a/mako-tools", 500),
                item("c/unrelated", 99999, description="other"),
                item("a/renderer", 600, description="MAKO extension"),
                item("z/MAKO", 10, archived=True),
            ],
            "mako",
        )
        self.assertEqual(
            [r["repository"] for r in rows],
            ["b/MAKO", "a/MAKO", "z/MAKO", "a/mako-tools", "a/renderer"],
        )
        self.assertTrue(rows[0]["fork"])
        self.assertTrue(rows[2]["archived"])

    def test_malformed_response_and_empty_cache(self):
        self.response.read.return_value = b'{"items": []}'
        self.assertEqual(self.finder.search("empty")["results"], [])
        self.finder.search("empty")
        self.assertEqual(self.opener.open.call_count, 1)
        self.response.read.return_value = b"[]"
        with self.assertRaises(ValueError):
            self.finder.search("malformed")

    def test_search_limit_isolated_from_core_and_cached_results_survive(self):
        self.authorize()
        self.opener.open.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "",
            {
                "X-RateLimit-Resource": "search",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(time.time() + 600),
            },
            None,
        )
        self.assertIn("limit", self.finder.search("another")["error"])
        calls = self.opener.open.call_count
        self.finder.search("third")
        self.assertEqual(calls, self.opener.open.call_count)
        self.assertEqual(len(self.finder.search("direct updater")["results"]), 1)
        self.assertLess(self.app.github.limits.get("core", 0), time.time())
        self.opener.open.side_effect = None
        self.response.read.return_value = json.dumps(item()).encode()
        self.assertEqual(len(self.finder.search("other/repo")["results"]), 1)

    def test_stale_results_offline(self):
        self.authorize()
        endpoint = next(key for key in self.app.state.data["cache"] if key.startswith("/search"))
        cached = self.app.state.get("cache", endpoint)
        self.app.state.put("cache", endpoint, {**cached, "time": 1})
        self.opener.open.side_effect = OSError("offline")
        result = self.finder.search("direct updater")
        self.assertEqual(len(result["results"]), 1)
        self.assertIsNotNone(result["error"])

    def test_search_cache_bounded(self):
        for index in range(45):
            self.finder.search("query " + str(index))
        entries = [v for v in self.app.state.data["cache"].values() if v.get("find_cache")]
        self.assertEqual(len(entries), 40)

    def test_details_root_and_nested_lazy_no_download(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        for nested in (False, True):
            with (
                self.project(nested),
                patch("direct_updater.find_plugins.stage_download") as download,
            ):
                detail = self.finder.details(REPO)
                self.assertEqual(detail["status"], "install")
                download.assert_not_called()
        self.assertEqual(self.opener.open.call_count, 1)

    def test_unavailable_missing_manifest_release_and_ambiguous_zip(self):
        self.authorize()
        with patch(
            "direct_updater.find_plugins.PublicGitHub.manifest",
            side_effect=GitHubError("not found"),
        ):
            self.assertEqual(self.finder.details(REPO)["status"], "unavailable")
        for releases in (
            [],
            [release(filename="Source.zip")],
            [release(assets=[release()["assets"][0], {**release()["assets"][0], "id": 21}])],
            [release(version="0.1.2-rc.1", prerelease=True)],
        ):
            self.app.github.releases = Mock(return_value=releases)
            with self.project():
                self.assertEqual(self.finder.details(REPO)["status"], "unavailable")

    def test_archived_disabled_never_fetch_manifest(self):
        for flag in ("archived", "disabled"):
            self.finder.known[REPO] = {
                "repository": REPO,
                flag: True,
                "archived": flag == "archived",
                "disabled": flag == "disabled",
            }
            with patch("direct_updater.find_plugins.PublicGitHub.manifest") as manifest:
                self.assertEqual(self.finder.details(REPO)["status"], "unavailable")
                manifest.assert_not_called()

    def test_installed_detection_update_current_version_and_source_conflict(self):
        folder = self.install()
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with self.project():
            self.assertEqual(self.finder.details(REPO)["status"], "update")
            package = json.loads((folder / "package.json").read_text())
            for version, status in (
                ("0.1.1", "current"),
                ("0.2.0", "current"),
                ("unknown", "version_unavailable"),
            ):
                (folder / "package.json").write_text(json.dumps({**package, "version": version}))
                self.assertEqual(self.finder.details(REPO)["status"], status)
            (folder / "package.json").write_text(
                json.dumps({**package, "repository": "someone/fork"})
            )
            self.assertEqual(self.finder.details(REPO)["status"], "unavailable")

    def staged(self, **kwargs):
        self.app.staging.mkdir(parents=True, exist_ok=True)
        path = self.app.staging / "update-test.zip"
        path.write_bytes(
            archive_bytes(
                extra={
                    "plugin/package.json": json.dumps(
                        {"name": kwargs.get("package", "decky-direct-updater"), "version": "0.1.1"}
                    )
                }
            )
        )
        return {"artifact": path.as_uri(), "name": NAME, "version": "0.1.1", "hash": "a" * 64}

    def test_new_install_completion_and_cancel_do_not_record_request_as_success(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with self.project():
            detail = self.finder.details(REPO)
            with patch("direct_updater.find_plugins.stage_download", return_value=self.staged()):
                staged = self.finder.stage(detail["token"], 10, 20)
            self.assertEqual(staged["install_type"], "install")
            self.assertFalse(self.finder.finish(staged["ticket"])["installed"])
            self.assertEqual(self.app.state.data["associations"], {})
            self.finder.finish(staged["ticket"], True)
            self.install(folder="plugin", version="0.1.1")
            self.assertFalse(self.finder.finish(staged["ticket"])["installed"])
            self.assertEqual(self.app.state.data["associations"], {})

    def test_successful_install_saves_actual_identity_confirmed_source(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with (
            self.project(),
            patch("direct_updater.find_plugins.stage_download", return_value=self.staged()),
        ):
            detail = self.finder.details(REPO)
            staged = self.finder.stage(detail["token"], 10, 20)
            self.install(folder="plugin", version="0.1.1")
            self.assertTrue(self.finder.finish(staged["ticket"])["installed"])
            self.assertEqual(self.app.state.get("associations", "plugin")["origin"], "confirmed")

    def test_stage_revalidates_ids_repository_and_package_identity(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with self.project():
            detail = self.finder.details(REPO)
            for token, rid, aid in (
                ("bad", 10, 20),
                (detail["token"], 11, 20),
                (detail["token"], 10, "https://evil"),
            ):
                with self.assertRaises(ValueError):
                    self.finder.stage(token, rid, aid)
            self.app.github.releases.return_value = [release(repository="other/fork")]
            with self.assertRaises(ValueError):
                self.finder.stage(detail["token"], 10, 20)
            self.app.github.releases.return_value = [release()]
            staged = self.staged(package="impostor")
            with patch("direct_updater.find_plugins.stage_download", return_value=staged):
                with self.assertRaisesRegex(ValueError, "identity"):
                    self.finder.stage(detail["token"], 10, 20)

    def test_update_reuses_generic_stage(self):
        self.install()
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with (
            self.project(),
            patch.object(self.app, "stage", return_value={"artifact": "validated"}) as stage,
        ):
            detail = self.finder.details(REPO)
            staged = self.finder.stage(detail["token"], 10, 20)
            stage.assert_called_once_with("updater", 10, 20)
            self.assertEqual(staged["install_type"], "update")

    def test_direct_normalization(self):
        self.assertEqual(
            query_identity("https://github.com/Nukeador/deckyup.git/"),
            ("nukeador/deckyup", True),
        )
        self.assertEqual(
            query_identity("https://github.com/Nukeador/decky-direct-updater.git/"),
            (REPO, True),
        )
        self.assertEqual(Version("0.1.1"), Version("v0.1.1"))

    def test_pagination_fetches_only_requested_page(self):
        self.response.read.return_value = json.dumps(
            {"items": [item(f"owner/direct-updater-{i}", i) for i in range(25)], "total_count": 75}
        ).encode()
        self.assertEqual(self.finder.search("direct updater")["next_page"], 2)
        self.assertEqual(self.opener.open.call_count, 1)
        self.finder.search("direct updater", 2)
        self.assertEqual(self.opener.open.call_count, 2)

    def test_cache_ttl_negative_ttl_and_etag_revalidation(self):
        self.authorize()
        endpoint = next(key for key in self.app.state.data["cache"] if key.startswith("/search"))
        cached = self.app.state.get("cache", endpoint)
        self.app.state.put("cache", endpoint, {**cached, "time": time.time() - 18000})
        self.finder.search("direct updater")
        self.assertEqual(self.opener.open.call_count, 1)
        self.app.state.put("cache", endpoint, {**cached, "time": 1})
        self.opener.open.side_effect = urllib.error.HTTPError("url", 304, "", {}, None)
        self.finder.search("direct updater")
        self.assertEqual(self.opener.open.call_args.args[0].get_header("If-none-match"), '"find"')
        self.opener.open.side_effect = None
        self.response.read.return_value = b'{"items": [], "total_count": 0}'
        self.finder.search("empty")
        endpoint = next(key for key in self.app.state.data["cache"] if "empty" in key)
        cached = self.app.state.get("cache", endpoint)
        self.app.state.put("cache", endpoint, {**cached, "time": time.time() - 1300})
        self.finder.search("empty")
        self.assertEqual(self.opener.open.call_count, 4)

    def test_zip_folder_collision_rejected_without_installed_writes(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        collision = self.root / "plugins" / "plugin"
        collision.mkdir()
        with (
            self.project(),
            patch("direct_updater.find_plugins.stage_download", return_value=self.staged()),
        ):
            detail = self.finder.details(REPO)
            with self.assertRaisesRegex(ValueError, "folder already exists"):
                self.finder.stage(detail["token"], 10, 20)
        self.assertEqual(list(collision.iterdir()), [])
        self.assertEqual(self.app.state.data["associations"], {})

    def test_completion_mismatched_identity_or_version_is_not_success(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with (
            self.project(),
            patch("direct_updater.find_plugins.stage_download", return_value=self.staged()),
        ):
            detail = self.finder.details(REPO)
            staged = self.finder.stage(detail["token"], 10, 20)
            folder = self.install(folder="plugin", version="0.1.0")
            self.assertFalse(self.finder.finish(staged["ticket"])["installed"])
            (folder / "package.json").write_text(
                json.dumps({"name": "impostor", "version": "0.1.1"})
            )
            self.assertFalse(self.finder.finish(staged["ticket"])["installed"])
            self.assertEqual(self.app.state.data["associations"], {})

    def test_manifest_identity_change_after_details_blocks_staging(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with self.project():
            detail = self.finder.details(REPO)
        with (
            self.project(package="another-package"),
            patch("direct_updater.find_plugins.stage_download") as download,
        ):
            with self.assertRaises(ValueError):
                self.finder.stage(detail["token"], 10, 20)
            download.assert_not_called()

    def test_zip_identity_and_version_discrepancies_reuse_existing_validator(self):
        self.authorize()
        self.app.github.releases = Mock(return_value=[release()])
        with self.project():
            detail = self.finder.details(REPO)
            for content in (archive_bytes(name="Impostor"), archive_bytes(version="9.9.9")):
                staged = self.staged()
                path = self.app.staging / "update-test.zip"
                path.write_bytes(content)
                with patch("direct_updater.find_plugins.stage_download", return_value=staged):
                    with self.assertRaises(ValueError):
                        self.finder.stage(detail["token"], 10, 20)
                self.assertFalse(path.exists())
