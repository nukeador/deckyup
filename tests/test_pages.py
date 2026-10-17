"""Static site and release verification tests, with no network requests."""

import hashlib
import html
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from direct_updater._html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_pages", ROOT / "scripts/build-pages.py")
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


def release(tag="v" + json.loads((ROOT / "package.json").read_text())["version"], **extra):
    return {
        "draft": False,
        "prerelease": False,
        "tag_name": tag,
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://github.com/{pages.REPOSITORY}/releases/download/{tag}/{name}",
            }
            for name in (pages.ASSET, "SHA256SUMS")
        ],
        **extra,
    }


def package():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        prefix = "decky-direct-updater/"
        for path in ("plugin.json", "package.json", "main.py", "LICENSE", "README.md"):
            archive.writestr(prefix + path, (ROOT / path).read_bytes())
        for path in (ROOT / "direct_updater").rglob("*.py"):
            archive.writestr(prefix + path.relative_to(ROOT).as_posix(), path.read_bytes())
        archive.writestr(
            prefix + "direct_updater/_html/LICENSE",
            (ROOT / "direct_updater/_html/LICENSE").read_bytes(),
        )
        archive.writestr(prefix + "dist/index.js", b"export default {};")
    return stream.getvalue()


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.ids, self.images, self.buttons, self.metas = [], [], [], [], []
        self.stack = []
        self.feed(html)
        if self.stack:
            raise AssertionError("Unclosed elements: " + str(self.stack))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in {"meta", "link", "img", "input", "br", "hr"}:
            self.stack.append(tag)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                raise AssertionError("Duplicate ID")
            self.ids.append(attrs["id"])
        if tag in {"a", "link", "script"}:
            destination = attrs.get("href", attrs.get("src"))
            if destination is not None:
                self.links.append(destination)
        if tag == "meta":
            self.metas.append(attrs)
        if tag == "img":
            self.images.append(attrs)
        if tag == "button":
            self.buttons.append(attrs)
        if tag == "input" and attrs.get("id") == "install-url":
            self.install_url = attrs["value"]

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise AssertionError("Unbalanced HTML: " + tag)


class Pages(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "_site"
        self.zip = package()
        self.release = release()
        self.corrupt = False
        self.checksum = hashlib.sha256(self.zip).hexdigest() + "  " + pages.ASSET + "\n"
        self.calls = []

    def fetch(self, url, destination, limit):
        self.calls.append(url)
        if url == pages.LATEST:
            content = json.dumps(self.release).encode()
        elif url.endswith("/SHA256SUMS"):
            content = self.checksum.encode()
        else:
            content = b"corrupt" if self.corrupt else self.zip
        self.assertLessEqual(len(content), limit)
        destination.write_bytes(content)

    def test_build_contains_exact_verified_release_bytes_and_real_images(self):
        result = pages.build(self.output, self.fetch)
        self.assertEqual((self.output / "install.zip").read_bytes(), self.zip)
        self.assertTrue(zipfile.is_zipfile(self.output / "install.zip"))
        self.assertEqual(result["sha256"], hashlib.sha256(self.zip).hexdigest())
        self.assertEqual(len(self.calls), 3)
        for image in pages.IMAGES:
            self.assertEqual(
                (self.output / "images" / image).read_bytes(),
                (ROOT / "docs/images" / image).read_bytes(),
            )
        self.assertTrue((self.output / ".nojekyll").is_file())
        self.assertEqual((self.output / "CNAME").read_text().strip(), "deckyup.nukeador.com")

    def test_favicon_and_social_preview_are_copied_and_linked(self):
        pages.build(self.output, self.fetch)
        markup = (self.output / "index.html").read_text()
        doc = Document(markup)
        self.assertIn('href="./favicon.svg"', markup)
        self.assertIn('href="./favicon-32.png"', markup)
        self.assertIn('href="./favicon.ico"', markup)
        self.assertIn("AGPL v3", markup)
        self.assertNotIn("AGPL-3.0-only", markup)
        self.assertIn(
            {
                "property": "og:image",
                "content": "https://deckyup.nukeador.com/social-preview.png",
            },
            doc.metas,
        )
        self.assertIn({"name": "twitter:card", "content": "summary_large_image"}, doc.metas)
        self.assertEqual(
            (self.output / "favicon.svg").read_bytes(),
            (ROOT / "site/favicon.svg").read_bytes(),
        )
        for filename in ("favicon-32.png", "favicon.ico", "social-preview.png"):
            self.assertEqual(
                (self.output / filename).read_bytes(),
                (ROOT / "site" / filename).read_bytes(),
            )
        social_png = (self.output / "social-preview.png").read_bytes()
        self.assertEqual(social_png[:8], b"\x89PNG\r\n\x1a\n")
        dimensions = (
            int.from_bytes(social_png[16:20], "big"),
            int.from_bytes(social_png[20:24], "big"),
        )
        self.assertEqual(dimensions, (1200, 630))

    def test_missing_duplicate_or_untrusted_assets_fail_without_output(self):
        for assets in (
            [],
            self.release["assets"][:1],
            self.release["assets"] * 2,
            [
                {**a, "browser_download_url": "https://evil.invalid/download"}
                for a in self.release["assets"]
            ],
        ):
            self.release["assets"] = assets
            with self.assertRaises(ValueError):
                pages.build(self.output, self.fetch)
            self.assertFalse(self.output.exists())

    def test_drafts_and_prereleases_cannot_be_public_installer(self):
        for data in (
            release(draft=True),
            release(prerelease=True),
            release("v0.2.0-rc.1"),
            release("nightly"),
        ):
            self.release = data
            with self.assertRaises(ValueError):
                pages.build(self.output, self.fetch)
        self.assertFalse(self.output.exists())

    def test_corrupt_download_preserves_previous_valid_output(self):
        pages.build(self.output, self.fetch)
        self.corrupt = True
        with self.assertRaisesRegex(ValueError, "checksum"):
            pages.build(self.output, self.fetch)
        self.assertEqual((self.output / "install.zip").read_bytes(), self.zip)

    def test_missing_duplicate_wrong_checksum_and_html_fail(self):
        for checksum in ("", "0" * 64 + "  install.zip\n", self.checksum * 2):
            self.checksum = checksum
            with self.assertRaises(ValueError):
                pages.build(self.output, self.fetch)
        self.zip = b"<!doctype html><html>redirect</html>"
        self.checksum = hashlib.sha256(self.zip).hexdigest() + "  " + pages.ASSET
        with self.assertRaisesRegex(ValueError, "package validation"):
            pages.build(self.output, self.fetch)
        self.assertFalse(self.output.exists())

    def test_site_html_structure_custom_domain_and_accessibility(self):
        pages.build(self.output, self.fetch)
        doc = Document((self.output / "index.html").read_text())
        self.assertEqual(doc.install_url, "https://deckyup.nukeador.com/install.zip")
        self.assertEqual(pages.REPOSITORY, "nukeador/deckyup")
        self.assertIn("https://github.com/nukeador/deckyup/releases", doc.links)
        downloads = [link for link in doc.links if link == "./install.zip"]
        self.assertEqual(len(downloads), 2)
        self.assertIn("#install", doc.links)
        self.assertEqual(sum("data-copy" in button for button in doc.buttons), 2)
        script = (ROOT / "site/script.js").read_text()
        self.assertIn("document.body.dataset.copyError", script)
        self.assertNotIn("Select and copy the installation URL below.", script)
        for link in doc.links:
            if link.startswith("#"):
                self.assertIn(link[1:], doc.ids)
            elif not urlsplit(link).scheme:
                self.assertFalse(link.startswith("/"), "Project Pages must use relative paths")
                self.assertTrue((self.output / link).exists(), link)
        for image in doc.images:
            if image.get("aria-hidden") == "true":
                self.assertEqual(image["alt"], "")
            else:
                self.assertGreater(len(image["alt"]), 3)
            self.assertIn("width", image)
            self.assertIn("height", image)
            self.assertTrue((self.output / image["src"]).is_file())

    def test_workflow_uses_trusted_main_and_successful_release_only(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text()
        for expected in (
            "workflow_dispatch:",
            "workflow_run:",
            'workflows: ["Deliberate version release"]',
            "conclusion == 'success'",
            "ref: main",
            "head_repository.full_name == github.repository",
            "persist-credentials: false",
            "pages: write",
            "id-token: write",
            "cancel-in-progress: false",
        ):
            self.assertIn(expected, workflow)
        self.assertNotIn("release: published", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("scripts/build-local.sh", workflow)
        self.assertNotIn("pull_request:", workflow)

    def test_all_ten_languages_are_complete_static_pages_with_one_installer(self):
        from scripts.site_locales import LOCALES

        pages.build(self.output, self.fetch)
        from scripts.site_locales import dictionaries

        translations = dictionaries(ROOT / "site")
        for code, (tag, _) in LOCALES.items():
            page = self.output / code / "index.html"
            markup = page.read_text()
            document = Document(markup)
            self.assertIn(f'lang="{tag}"', markup)
            self.assertIn('data-default-entry="false"', markup)
            self.assertNotIn("{{", markup)
            self.assertIn('href="../install.zip"', markup)
            self.assertIn('href="#install"', markup)
            self.assertIn('href="../favicon.svg"', markup)
            self.assertIn('href="../favicon-32.png"', markup)
            self.assertIn('href="../favicon.ico"', markup)
            self.assertEqual(markup.count("var _paq = (window._paq = window._paq || []);"), 1)
            self.assertIn('_paq.push(["trackPageView"]);', markup)
            self.assertIn('_paq.push(["enableLinkTracking"]);', markup)
            self.assertIn('var u = "//stats.nukeador.com/";', markup)
            self.assertIn('u + "matomo.php"', markup)
            self.assertIn('_paq.push(["setSiteId", "31"]);', markup)
            self.assertIn('g.src = u + "matomo.js";', markup)
            self.assertIn(
                {
                    "property": "og:image",
                    "content": "https://deckyup.nukeador.com/social-preview.png",
                },
                document.metas,
            )
            self.assertIn(
                f'data-copy-error="{html.escape(translations[code]["copy_error"], quote=True)}"',
                markup,
            )
            self.assertIn(html.escape(translations[code]["how_install"]), markup)
            self.assertIn(html.escape(translations[code]["community"]), markup)
            self.assertIn("AGPL v3", markup)
            self.assertNotIn("AGPL-3.0-only", markup)
            self.assertIn('src="../images/find-plugins.png"', markup)
            self.assertIn('href="../' + code + '/"', markup)
            self.assertEqual(document.install_url, "https://deckyup.nukeador.com/install.zip")
            for link in document.links:
                if link.startswith("#"):
                    self.assertIn(link[1:], document.ids)
                elif not urlsplit(link).scheme:
                    self.assertTrue((page.parent / link).exists(), f"{code}: {link}")
            self.assertEqual(markup.count('rel="alternate"'), 11)
        root_markup = (self.output / "index.html").read_text()
        self.assertEqual(root_markup.count("var _paq = (window._paq = window._paq || []);"), 1)
        self.assertEqual(len(list(self.output.glob("**/install.zip"))), 1)

    def test_missing_translation_fails_instead_of_silently_showing_english(self):
        from scripts.site_locales import dictionaries

        source = Path(self.temporary.name) / "translations"
        (source / "locales").mkdir(parents=True)
        for path in (ROOT / "site/locales").glob("*.json"):
            entries = json.loads(path.read_text())
            if path.stem == "ja":
                del entries["developers_text"]
            (source / "locales" / path.name).write_text(json.dumps(entries))
        with self.assertRaisesRegex(ValueError, "ja"):
            dictionaries(source)
