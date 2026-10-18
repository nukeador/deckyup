import json
from unittest.mock import Mock, patch

from direct_updater.github_releases import GitHub, GitHubError
from direct_updater.github_web import PublicGitHub
from direct_updater.installed_plugins import repository, source_from_metadata
from direct_updater.official_database import parse_gitmodules
from direct_updater.source_discovery import AUTO_SEARCHES
from direct_updater.state import State
from test_updater import Workspace, NAME, REPO, release


class Discovery(Workspace):
    def app(self):
        app = self.updater()
        app.github.releases = Mock(return_value=[release()])
        app.github.search = Mock(return_value=[])
        return app

    def metadata(self, folder, **fields):
        path = folder / "package.json"
        metadata = json.loads(path.read_text())
        path.write_text(json.dumps({**metadata, **fields}))

    def test_first_launch_automatically_saves_clear_metadata_then_checks_releases(self):
        self.install()
        app = self.app()
        with patch("direct_updater.plugin_updates.stage_download") as stage:
            result = app.check()
        self.assertEqual(result[0]["status"], "update")
        record = app.state.get("associations", "updater")
        self.assertEqual(record["source"], REPO)
        self.assertEqual(record["origin"], "metadata")
        app.github.search.assert_not_called()
        app.github.matches_manifest.assert_not_called()
        stage.assert_not_called()
        self.assertEqual(self.updater().list_plugins()[0]["source"], REPO)

    def test_secondary_metadata_and_plugin_manifest_are_checked(self):
        folder = self.install(repo=None)
        self.metadata(
            folder,
            homepage="https://github.com/owner/project",
            bugs={"url": "https://github.com/owner/project/issues"},
        )
        app = self.app()
        self.assertIsNone(app.list_plugins()[0]["source"])
        self.assertEqual(app.check()[0]["source"], "owner/project")
        app.github.matches_manifest.assert_called_with("owner/project", NAME)
        folder2 = self.install("another", "Other plugin", repo=None)
        (folder2 / "plugin.json").write_text(
            json.dumps(
                {"name": "Other plugin", "repository": {"url": "https://github.com/dev/other"}}
            )
        )
        self.assertEqual(
            next(p for p in app.check() if p["id"] == "another")["source"], "dev/other"
        )

    def test_official_database_requires_directory_or_package_and_manifest_identity(self):
        self.install(repo=None)
        app = self.app()
        app.github.official_sources.return_value = {"updater": [REPO]}
        self.assertEqual(app.check()[0]["source"], REPO)
        self.assertEqual(app.state.get("associations", "updater")["origin"], "official_database")
        app.github.matches_manifest.assert_called_with(REPO, NAME)
        app.github.search.assert_not_called()

    def test_display_name_alone_does_not_bind_an_official_or_stale_source(self):
        self.install("unrelated-folder", "Other Plugin", repo=None)
        app = self.app()
        app.github.official_sources.return_value = {"other plugin": ["dev/other"]}
        app.state.put("sources", "Other Plugin", "old/project")
        app.github.search.return_value = [{"repository": "old/project"}]
        plugin = app.check()[0]
        self.assertIsNone(plugin["source"])
        self.assertEqual(plugin["status"], "source_suggested")
        self.assertIsNone(app.state.get("associations", "unrelated-folder"))

    def test_conflicting_metadata_and_official_fork_require_confirmation(self):
        self.install()
        app = self.app()
        app.github.official_sources.return_value = {"updater": ["fork/decky-direct-updater"]}
        result = app.check()[0]
        self.assertIsNone(result["source"])
        self.assertEqual(result["status"], "source_suggested")
        self.assertEqual(
            {c["repository"] for c in result["suggestions"]}, {REPO, "fork/decky-direct-updater"}
        )
        app.github.releases.assert_not_called()
        app.github.search.assert_not_called()
        app.confirm("updater", "fork/decky-direct-updater")
        app.check()
        self.assertEqual(app.list_plugins()[0]["source"], "fork/decky-direct-updater")
        self.assertEqual(app.state.get("associations", "updater")["origin"], "confirmed")

    def test_alias_redirect_is_not_a_conflicting_fork(self):
        self.install()
        app = self.app()
        canonical = "newowner/decky-direct-updater"
        app.github.official_sources.return_value = {"updater": [canonical]}
        app.github.canonical_repository.side_effect = lambda repo: canonical
        self.assertEqual(app.check()[0]["source"], canonical)
        self.assertFalse(app.list_plugins()[0]["suggestions"])

    def test_confirmed_mapping_survives_metadata_and_database_changes(self):
        folder = self.install(repo=None)
        app = self.app()
        app.github.search.return_value = [{"repository": "my/fork"}]
        app.search("updater")
        app.confirm("updater", "my/fork")
        self.metadata(folder, version="0.1.1", repository="other/project")
        app.github.official_sources.return_value = {"updater": [REPO]}
        app.check()
        self.assertEqual(app.list_plugins()[0]["source"], "my/fork")
        app.github.official_sources.assert_not_called()
        recreated = self.updater()
        self.assertEqual(recreated.list_plugins()[0]["source"], "my/fork")

    def test_searches_are_cached_including_empty_results_and_after_reloading(self):
        self.install(repo=None)
        app = self.app()
        self.assertEqual(app.check()[0]["status"], "source_not_found")
        app.check()
        app.github.search.assert_called_once()
        restarted = self.app()
        restarted.check()
        restarted.github.search.assert_not_called()
        restarted.search("updater")
        restarted.github.search.assert_called_once()

    def test_successful_search_is_only_a_suggestion_and_persists_for_one_click_confirmation(self):
        self.install(repo=None)
        app = self.app()
        app.github.search.return_value = [
            {"repository": "dev/project", "description": "Decky plugin"}
        ]
        result = app.check()[0]
        self.assertEqual(result["status"], "source_suggested")
        self.assertIsNone(result["source"])
        app.github.releases.assert_not_called()
        restarted = self.app()
        restarted.confirm("updater", "dev/project")
        self.assertEqual(restarted.check()[0]["source"], "dev/project")
        restarted.github.search.assert_not_called()

    def test_budget_and_priority_defer_extra_searches_to_find_source(self):
        self.install()
        for index in range(5):
            self.install(f"unknown-{index}", f"Unknown {index}", repo=None)
        app = self.app()
        order = []
        app.github.releases.side_effect = lambda *args, **kwargs: order.append("release") or [
            release()
        ]
        app.github.search.side_effect = lambda *args: order.append("search") or []
        app.check()
        self.assertEqual(order[0], "release")
        self.assertEqual(app.github.search.call_count, AUTO_SEARCHES)
        app.check()
        self.assertEqual(app.github.search.call_count, AUTO_SEARCHES)
        app.search("unknown-4")
        self.assertEqual(app.github.search.call_count, AUTO_SEARCHES + 1)

    def test_new_removed_changed_and_reused_directory_plugins(self):
        folder = self.install("unknown", "Unknown", repo=None)
        app = self.app()
        app.check()
        self.install("new", "New plugin", repo=REPO)
        result = app.check()
        self.assertEqual({p["id"] for p in result}, {"unknown", "new"})
        self.metadata(folder, repository=REPO)
        app.check()
        self.assertEqual(app.plugin("unknown")["source"], REPO)
        app.discovery.save(app.plugin("unknown"), "explicit/source", "confirmed")
        (folder / "plugin.json").write_text(json.dumps({"name": "Different plugin"}))
        self.metadata(folder, name="different-package", repository=None)
        self.assertIsNone(app.plugin("unknown")["source"])
        # Disappeared plugins do not come from the saved association catalogue.
        import shutil

        shutil.rmtree(folder)
        self.assertEqual([p["id"] for p in app.list_plugins()], ["new"])

    def test_stale_search_candidate_is_not_confirmable_after_metadata_changes(self):
        folder = self.install(repo=None)
        app = self.app()
        app.github.search.return_value = [{"repository": "dev/project"}]
        app.search("updater")
        self.metadata(folder, homepage="https://github.com/another/project")
        with self.assertRaisesRegex(ValueError, "verified suggestions"):
            app.confirm("updater", "dev/project")

    def test_offline_and_rate_limits_leave_inventory_and_previous_sources_usable(self):
        self.install()
        self.install("unknown", "Unknown", repo=None)
        app = self.app()
        app.check()
        app.github.official_sources.side_effect = OSError("Offline")
        app.github.releases.side_effect = GitHubError("Offline")
        app.discovery.remaining_searches = AUTO_SEARCHES
        app.github.search.side_effect = GitHubError("GitHub rate limit reached; retry in 2 min")
        # Force the unknown entry's prior negative search to expire.
        unknown = app.plugin("unknown")
        app.discovery.remember(unknown, search_time=0)
        result = app.check()
        self.assertEqual(len(result), 2)
        self.assertEqual(next(p for p in result if p["id"] == "updater")["source"], REPO)
        self.assertIn("rate limit", app.plugin("unknown")["discovery_error"])
        requests = app.github.search.call_count
        app.check()
        self.assertEqual(app.github.search.call_count, requests)

    def test_manual_entry_must_verify_and_still_requires_confirmation(self):
        self.install(repo=None)
        app = self.app()
        for invalid in (
            "https://evil.org/project",
            "SteamDeckHomebrew/decky-plugin-template",
            "https://github.com@evil.org/a/b",
        ):
            with self.assertRaises(ValueError):
                app.verify_source("updater", invalid)
        app.github.matches_manifest.return_value = False
        with self.assertRaisesRegex(ValueError, "manifest"):
            app.verify_source("updater", "owner/project")
        app.github.matches_manifest.return_value = True
        candidates = app.verify_source("updater", "https://github.com/owner/project")
        self.assertEqual(candidates[0]["owner"], "owner")
        self.assertIsNone(app.plugin("updater")["source"])
        app.confirm("updater", "owner/project")
        self.assertEqual(app.plugin("updater")["source"], "owner/project")

    def test_templates_and_invalid_identity_are_never_automatically_linked(self):
        folder = self.install(repo="SteamDeckHomebrew/decky-plugin-template")
        app = self.app()
        app.check()
        self.assertIsNone(app.plugin("updater")["source"])
        app.github.releases.assert_not_called()
        (folder / "plugin.json").unlink()
        self.metadata(folder, repository=REPO)
        self.assertEqual(app.list_plugins(), [])
        (folder / "plugin.json").write_text("{invalid")
        self.assertIsNone(app.list_plugins()[0]["source"])
        app.github.releases.assert_not_called()

    def test_no_reverification_for_unchanged_plugins_but_changed_metadata_retries(self):
        folder = self.install(repo="owner/unmatched-project")
        app = self.app()
        app.check()
        count = app.github.matches_manifest.call_count
        app.check()
        self.assertEqual(app.github.matches_manifest.call_count, count)
        self.metadata(folder, repository="other/new-project")
        app.check()
        self.assertGreater(app.github.matches_manifest.call_count, count)


class Database(Workspace):
    def test_gitmodules_parse_filters_templates_foreign_hosts_and_ambiguous_paths(self):
        parsed = parse_gitmodules("""[submodule "plugins/A"]
path = plugins/A
url = git@github.com:owner/plugin.git
[submodule "plugins/B"]
path = plugins/A
url = https://github.com/fork/plugin
[submodule "plugins/C"]
path = plugins/C
url = https://gitlab.com/other/project
[submodule "plugins/template"]
path = plugins/template
url = https://github.com/dev/decky-plugin-template
""")
        self.assertEqual(parsed, {"a": ["owner/plugin", "fork/plugin"]})
        for value in (
            "git://github.com/owner/plugin.git",
            "ssh://git@github.com/owner/plugin.git",
            " https://github.com/owner/plugin ",
        ):
            self.assertEqual(repository(value), "owner/plugin")
        self.assertEqual(
            source_from_metadata({"repository": "dev/decky-plugin-template"}), (None, None)
        )

    def test_official_database_uses_existing_web_cache_and_retains_stale_data_offline(self):
        github = GitHub(State(self.root / "state"))
        text = '[submodule "plugins/A"]\npath=plugins/A\nurl=https://github.com/owner/plugin\n'
        with patch.object(PublicGitHub, "text", return_value=text) as read:
            self.assertEqual(github.official_sources(), {"a": ["owner/plugin"]})
            github.official_sources()
            read.assert_called_once()
        cached = github.state.get("cache", "_official_database_v1")
        cached["time"] = 0
        with patch.object(PublicGitHub, "text", side_effect=OSError("Offline")) as read:
            self.assertEqual(github.official_sources(), {"a": ["owner/plugin"]})
            github.official_sources()
            read.assert_called_once()

    def test_corrupt_database_format_is_backed_off_without_blocking(self):
        github = GitHub(State(self.root / "state"))
        with patch.object(PublicGitHub, "text", return_value="not a submodule index") as read:
            self.assertEqual(github.official_sources(), {})
            self.assertEqual(github.official_sources(), {})
            read.assert_called_once()


class SearchHints(Workspace):
    def test_author_hint_finds_compact_repository_names_without_extra_search_budget(self):
        github = GitHub(State(self.root / "state"))
        github.matches_manifest = Mock(return_value=True)
        github.releases = Mock(return_value=[])
        github.get = Mock(
            return_value={
                "items": [
                    {
                        "full_name": "ExampleAuthor/DeckyHelixSRManager",
                        "description": "Decky plugin",
                    }
                ]
            }
        )
        result = github.search(
            {"name": "HelixSR Manager", "package_name": "decky-helixsr", "author": "ExampleAuthor"}
        )
        self.assertEqual(result[0]["repository"], "ExampleAuthor/DeckyHelixSRManager")
        self.assertIn("helixsr%20user%3AExampleAuthor", github.get.call_args.args[0])
        github.get.assert_called_once()
        github.matches_manifest.assert_called_with(
            "ExampleAuthor/DeckyHelixSRManager", "HelixSR Manager"
        )

    def test_search_response_cannot_supply_arbitrary_repositories_or_urls(self):
        github = GitHub(State(self.root / "state"))
        github.matches_manifest = Mock(return_value=True)
        github.releases = Mock(return_value=[])
        github.get = Mock(
            return_value={
                "items": [{"full_name": "https://evil.org/repo"}, {"full_name": "owner/../etc"}]
            }
        )
        self.assertEqual(github.search({"name": NAME}), [])
        github.matches_manifest.assert_not_called()

    def test_matching_releases_help_rank_candidates_without_downloading_zips(self):
        github = GitHub(State(self.root / "state"))
        github.get = Mock(
            return_value={"items": [{"full_name": "dev/no-releases"}, {"full_name": "dev/plugin"}]}
        )
        github.matches_manifest = Mock(return_value=True)
        github.releases = Mock(
            side_effect=lambda repo, **kwargs: [release()] if repo == "dev/plugin" else []
        )
        result = github.search({"name": NAME, "package_name": "decky-direct-updater"})
        self.assertEqual(result[0]["repository"], "dev/plugin")
        self.assertTrue(result[0]["compatible_release"])
        self.assertEqual(github.releases.call_count, 2)
