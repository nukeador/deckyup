import tempfile
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch
from pathlib import Path

from direct_updater.github_releases import GitHub, GitHubError, compatible_releases
from direct_updater.github_web import AssetPage, FILTER, PublicGitHub, ReleasePage
from direct_updater.state import State
from direct_updater.package_validation import stage_download

REPO = "owner/plugin"


def page(tags=("v1.2.3",)):
    return (
        '<input id="release-filter" value="'
        + FILTER
        + '">'
        + "".join(
            f'<section data-release-anchor="release-{tag}"><include-fragment src="https://github.com/{REPO}/releases/expanded_assets/{tag}"></include-fragment></section>'
            for tag in tags
        )
    )


def assets(tag="v1.2.3"):
    return f'<ul><li><a href="/{REPO}/releases/download/{tag}/Plugin.zip">Plugin.zip</a><clipboard-copy value="sha256:{"a" * 64}"></clipboard-copy></li><li><a href="/{REPO}/archive/refs/tags/{tag}.zip">Source code</a></li></ul>'


class Web(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = State(self.temporary.name)
        self.client = PublicGitHub(self.state)
        self.client.opener = Mock()

    def response(self, value, url):
        response = Mock()
        response.headers = {"ETag": '"web"'}
        response.read.return_value = value.encode()
        response.geturl.return_value = url
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_filtered_release_page_semver_order_and_prerelease(self):
        parser = ReleasePage(REPO)
        parser.feed(page(("v1.2.9", "v1.2.10", "v2.0.0-rc.1", "render-v8.0.0")))
        self.assertEqual(parser.versions(), ["v1.2.10", "v1.2.9"])
        parser = ReleasePage(REPO)
        parser.feed(
            page().replace(
                "<include-fragment", '<span class="Label">Pre-release</span><include-fragment'
            )
        )
        self.assertEqual(parser.versions(), [])

    def test_unknown_html_or_missing_stable_filter_fails_closed(self):
        for html in [
            page().replace(FILTER, ""),
            "<html>New website</html>",
            f'<input id="release-filter" value="{FILTER}">',
        ]:
            parser = ReleasePage(REPO)
            parser.feed(html)
            with self.assertRaises(GitHubError):
                parser.versions()

    def test_empty_repository_is_not_fatal(self):
        parser = ReleasePage(REPO)
        parser.feed("<div>There aren’t any releases here</div>")
        self.assertEqual(parser.versions(), [])

    def test_non_semver_release_is_unavailable_not_missing(self):
        with patch.object(self.client, "text", return_value=page(("nightly",))):
            releases = self.client.releases(REPO)
        self.assertEqual(releases[0]["tag_name"], "nightly")
        self.assertEqual(compatible_releases({"name": "Plugin"}, releases), ([], False))

    def test_ambiguous_asset_does_not_stop_release_search(self):
        plugin = {"name": "Plugin Updater", "package_name": "plugin-updater"}
        html = page(("v2.0.0", "v1.2.3"))
        ambiguous = (
            assets("v2.0.0")
            .replace("Plugin.zip", "Plugin-Updater.zip")
            .replace(
                "</ul>",
                '<li><a href="/owner/plugin/releases/download/v2.0.0/Plugin-Updater-v2.0.0.zip">Plugin-Updater-v2.0.0.zip</a></li></ul>',
            )
        )

        def read(url, refresh=False):
            if "expanded_assets/v2.0.0" in url:
                return ambiguous
            if "expanded_assets/v1.2.3" in url:
                return assets("v1.2.3").replace("Plugin.zip", "Plugin-Updater.zip")
            return html

        with patch.object(self.client, "text", side_effect=read) as request:
            result = self.client.releases(REPO, plugins=[plugin])
        self.assertEqual(compatible_releases(plugin, result), ([], True))
        self.assertEqual(len(result), 2)
        self.assertTrue(
            any("expanded_assets/v1.2.3" in call.args[0] for call in request.call_args_list)
        )

    def test_assets_are_bound_to_repo_tag_and_digest(self):
        parser = AssetPage(REPO, "v1.2.3")
        parser.feed(assets())
        self.assertEqual(len(parser.assets), 1)
        asset = parser.assets[0]
        self.assertEqual(asset["id"], "Plugin.zip")
        self.assertEqual(asset["digest"], "sha256:" + "a" * 64)
        self.assertIsNone(asset["size"])
        for invalid in [
            assets().replace("/owner/plugin/releases/download", "/evil/repo/releases/download"),
            assets("v9.0.0"),
        ]:
            parser = AssetPage(REPO, "v1.2.3")
            parser.feed(invalid)
            self.assertEqual(parser.assets, [])

    def test_ambiguous_digest_is_rejected(self):
        parser = AssetPage(REPO, "v1.2.3")
        with self.assertRaises(GitHubError):
            parser.feed(
                assets().replace(
                    "</li>", f'<clipboard-copy value="sha256:{"b" * 64}"></clipboard-copy></li>', 1
                )
            )

    def test_cache_and_refresh_cooldown_do_not_spend_rest_quota(self):
        url = "https://github.com/owner/plugin/releases?q=test"
        self.state.put("cache", "_rate_core", {"until": time.time() + 3600})
        self.client.opener.open.return_value = self.response(page(), url)
        self.client.text(url)
        self.client.text(url, True)
        self.assertEqual(self.client.opener.open.call_count, 1)
        self.state.data["cache"][url]["time"] -= 61
        self.client.opener.open.side_effect = urllib.error.HTTPError(url, 304, "", {}, None)
        self.assertEqual(self.client.text(url, True), page())
        self.assertEqual(self.client.opener.open.call_count, 2)

    def test_negative_manifest_cache_and_web_backoff(self):
        url = "https://raw.githubusercontent.com/owner/plugin/HEAD/plugin.json"
        self.client.opener.open.side_effect = urllib.error.HTTPError(url, 404, "", {}, None)
        for _ in range(2):
            with self.assertRaises(GitHubError):
                self.client.text(url)
        self.assertEqual(self.client.opener.open.call_count, 1)
        other = "https://github.com/owner/plugin/releases"
        self.client.opener.open.side_effect = urllib.error.HTTPError(
            other, 429, "", {"Retry-After": "120"}, None
        )
        with self.assertRaises(GitHubError):
            self.client.text(other)
        client = PublicGitHub(self.state)
        client.opener = Mock()
        with self.assertRaisesRegex(GitHubError, "retry in"):
            client.text(other)
        client.opener.open.assert_not_called()

    def test_release_lookup_uses_public_web_even_when_rest_is_exhausted(self):
        self.state.put("cache", "_rate_core", {"until": time.time() + 3600})
        github = GitHub(self.state)
        github.get = Mock(side_effect=AssertionError("REST must not be used"))
        with patch.object(PublicGitHub, "text", side_effect=[page(), assets()]) as read:
            releases = github.releases(REPO)
        self.assertEqual(releases[0]["tag_name"], "v1.2.3")
        self.assertTrue(all("api.github.com" not in call.args[0] for call in read.call_args_list))
        github.get.assert_not_called()

    def test_helix_exact_display_name_allows_different_package_name(self):
        plugin = {"name": "HelixSR Manager", "package_name": "decky-helixsr-manager"}
        releases = [
            {
                "id": "v0.10.2",
                "tag_name": "v0.10.2",
                "assets": [{"id": "HelixSR-Manager.zip", "name": "HelixSR-Manager.zip"}],
            }
        ]
        self.assertEqual(len(compatible_releases(plugin, releases)[0]), 1)

    def test_unknown_download_size_is_bounded_by_actual_content_length(self):
        from test_updater import archive_bytes, NAME

        data = archive_bytes()
        asset = {
            "browser_download_url": "https://github.com/owner/plugin/releases/download/v0.1.1/Plugin.zip",
            "size": None,
        }
        response = Mock()
        response.headers = {"Content-Length": str(len(data))}
        response.geturl.return_value = asset["browser_download_url"]
        response.read.side_effect = [data, b""]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            staged = stage_download(
                asset, REPO, NAME, "0.1.1", Path(self.temporary.name) / "staged"
            )
        self.assertTrue(Path(staged["artifact"][7:]).exists())


class RestBudget(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = State(self.temporary.name)

    def test_exhausted_core_does_not_block_repository_search_bucket(self):
        self.state.put("cache", "_rate_core", {"until": time.time() + 3600})
        client = GitHub(self.state)
        client.opener = Mock()
        response = Mock()
        response.headers = {}
        response.read.return_value = b'{"items":[]}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client.opener.open.return_value = response
        self.assertEqual(client.get("/search/repositories?q=test"), {"items": []})
        client.opener.open.assert_called_once()

    def test_retry_delay_survives_restarting_client(self):
        client = GitHub(self.state)
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError(
            "url", 429, "", {"Retry-After": "120"}, None
        )
        with self.assertRaisesRegex(GitHubError, "retry in"):
            client.get("/search/repositories?q=test")
        restarted = GitHub(self.state)
        restarted.opener = Mock()
        with self.assertRaisesRegex(GitHubError, "retry in"):
            restarted.get("/search/repositories?q=other")
        restarted.opener.open.assert_not_called()

    def test_plain_permission_403_is_not_misreported_as_rate_limit(self):
        client = GitHub(self.state)
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.HTTPError("url", 403, "", {}, None)
        with self.assertRaisesRegex(GitHubError, "denied"):
            client.get("/search/repositories?q=test")
        self.assertFalse(client.limits)
