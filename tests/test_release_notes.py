"""Optional release notes stay inert, bounded and attached to the exact release."""

from unittest import TestCase

from direct_updater.github_web import ReleasePage, MAX_NOTES
from direct_updater.plugin_updates import Updater
from direct_updater.release_selection import release_option
from test_github_web import REPO, page
from test_updater import release


def html_notes(body, tag="v1.2.3"):
    return page((tag,)).replace(
        "<include-fragment", f'<div class="markdown-body">{body}</div><include-fragment'
    )


class NotesParsing(TestCase):
    def parse(self, body):
        parser = ReleasePage(REPO)
        parser.feed(html_notes(body))
        self.assertEqual(parser.versions(), ["v1.2.3"])
        return parser.release_notes("v1.2.3")

    def test_readable_paragraphs_headings_lists_and_code(self):
        result = self.parse(
            "<h2>Changes</h2><p>First &amp; better</p><p>Second</p><ul><li>Fix <b>audio</b></li><li>Add input</li></ul><ol><li>Restart</li></ol><pre><code>example()</code></pre>"
        )
        self.assertEqual(
            result["notes"],
            "Changes\nFirst & better\nSecond\n• Fix audio\n• Add input\n• Restart\nexample()",
        )
        self.assertFalse(result["notes_truncated"])

    def test_single_empty_and_unusual_markup(self):
        self.assertEqual(self.parse("<p>One paragraph</p>")["notes"], "One paragraph")
        self.assertEqual(self.parse("")["notes"], "")
        self.assertEqual(self.parse("<p>Unclosed <b>format")["notes"], "Unclosed format")
        parser = ReleasePage(REPO)
        parser.feed(page())
        self.assertEqual(parser.release_notes("v1.2.3")["notes"], "")

    def test_active_markup_images_tables_and_controls_removed(self):
        result = self.parse(
            '<script>alert(1)</script><style>secret</style><iframe>embed</iframe><table><tr><td>table</td></tr></table><img alt="badge" src="evil"><p>Good\u200b\x00 &lt;script&gt; <a href="javascript:evil()">label</a></p>'
        )
        self.assertEqual(result["notes"], "Good <script> label")
        self.assertNotIn("javascript:", str(result))
        self.assertEqual(
            result["release_url"], "https://github.com/owner/plugin/releases/tag/v1.2.3"
        )

    def test_unclosed_note_container_does_not_hide_assets(self):
        parser = ReleasePage(REPO)
        parser.feed(
            page().replace(
                "<include-fragment", '<div class="markdown-body"><p>Broken<include-fragment'
            )
        )
        self.assertEqual(parser.versions(), ["v1.2.3"])
        self.assertEqual(parser.release_notes("v1.2.3")["notes"], "Broken")

    def test_notes_cannot_supply_release_metadata(self):
        parser = ReleasePage(REPO)
        parser.feed(
            html_notes(
                '<span class="Label">Pre-release</span><include-fragment src="https://github.com/owner/plugin/releases/expanded_assets/forged"></include-fragment><p>Body</p>'
            )
        )
        self.assertEqual(parser.versions(), ["v1.2.3"])
        self.assertEqual(parser.tags, ["v1.2.3"])

    def test_large_notes_are_bounded(self):
        for body in ("<p>" + "x" * 50000 + "</p>", "<p>Item</p>" * 2000):
            result = self.parse(body)
            self.assertTrue(result["notes_truncated"])
            self.assertLessEqual(len(result["notes"]), MAX_NOTES)
            self.assertLessEqual(len(result["notes"].splitlines()), 100)
            self.assertTrue(all(len(line) <= 600 for line in result["notes"].splitlines()))

    def test_multiple_releases_malformed_notes_and_prerelease_binding(self):
        parser = ReleasePage(REPO)
        parser.feed(
            html_notes("<p>Stable", "v1.2.3") + html_notes("<p>Beta only</p>", "v2.0.0-rc.1")
        )
        self.assertEqual(parser.release_notes("v1.2.3")["notes"], "Stable")
        self.assertEqual(parser.release_notes("v2.0.0-rc.1")["notes"], "Beta only")
        self.assertEqual(parser.versions(), ["v1.2.3"])

    def test_automatic_and_manual_propagation(self):
        first = release("2.0.0")
        first.update(
            notes="Selected notes",
            notes_truncated=False,
            release_url="https://github.com/owner/plugin/releases/tag/2.0.0",
        )
        other = release("1.5.0")
        other["notes"] = "Other notes"
        plugin = {
            "name": "Decky Direct Updater",
            "package_name": "decky-direct-updater",
            "version": "1.0.0",
            "source": REPO,
        }
        result = Updater.resolve(None, plugin, [other, first])
        self.assertEqual(result["release_notes"]["notes"], "Selected notes")
        self.assertEqual(release_option(plugin, other)["release_notes"]["notes"], "Other notes")
