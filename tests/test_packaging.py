"""Exercise packaged backends in isolated Loader-like subprocesses."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class Packaging(unittest.TestCase):
    def test_production_is_deterministic_and_excludes_fixtures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.project(root)
            packaging = self.packager()
            with patch.object(packaging, "ROOT", project):
                first = packaging.package(root / "first.zip")
                second = packaging.package(root / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertFalse(any("fixture_backend" in name for name in archive.namelist()))
                main = archive.read("decky-direct-updater/main.py").decode()
                self.assertIn("from direct_updater.plugin_updates import Updater", main)
                self.assertNotIn("FixtureUpdater", main)
                self.assertFalse(any("tests/" in name for name in archive.namelist()))

    def project(self, root):
        project = root / "project"
        project.mkdir()
        for filename in ("package.json", "plugin.json", "main.py", "LICENSE", "README.md"):
            shutil.copyfile(ROOT / filename, project / filename)
        shutil.copytree(
            ROOT / "direct_updater",
            project / "direct_updater",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        (project / "dist").mkdir()
        (project / "dist/index.js").write_text("export default () => ({});\n")
        return project

    def packager(self):
        spec = importlib.util.spec_from_file_location("local_packager", ROOT / "scripts/package.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_packaged_parser_works_without_optional_decky_stdlib_modules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.project(root)
            packaging = self.packager()
            with patch.object(packaging, "ROOT", project):
                package = packaging.package(root / "plugin.zip")
            script = r"""
import importlib.abc, sys
class MissingDeckyModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "html" or fullname.startswith("html.") or fullname == "_markupbase":
            raise ModuleNotFoundError("Not bundled by Decky: " + fullname)
sys.meta_path.insert(0, MissingDeckyModules())
sys.path.insert(0, sys.argv[1] + "/decky-direct-updater")
from direct_updater.github_web import ReleasePage, AssetPage, FILTER
from direct_updater._html import unescape
assert unescape("&amp;&#x27;&copy;") == "&'©"
release = ReleasePage("owner/repo")
release.feed('<input id="release-filter" value="' + FILTER + '"><section data-release-anchor="release-v1.2.3"><include-fragment src="https://github.com/owner/repo/releases/expanded_assets/v1.2.3"></include-fragment></section>')
assert release.versions() == ["v1.2.3"]
asset = AssetPage("owner/repo", "v1.2.3")
asset.feed('<ul><li><a href="/owner/repo/releases/download/v1.2.3/Plugin.zip">Plugin.zip</a></li></ul>')
assert asset.assets[0]["name"] == "Plugin.zip"
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(package)],
                capture_output=True,
                text=True,
                cwd=root,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_two_version_self_update_and_persistent_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = self.project(root)
            packaging = self.packager()
            fixture = (ROOT / "scripts/fixture_backend.py.txt").read_bytes()
            with patch.object(packaging, "ROOT", project):
                old = packaging.package(root / "old.zip", "0.1.0", fixture)
                new = packaging.package(root / "Decky-Direct-Updater-v0.1.1.zip", "0.1.1", fixture)
            plugins = root / "plugins"
            with zipfile.ZipFile(old) as archive:
                archive.extractall(plugins)
            runtime = root / "runtime"
            local = runtime / "local-fixture"
            local.mkdir(parents=True)
            shutil.copyfile(new, local / new.name)
            (local / "release.json").write_text(
                json.dumps(
                    [
                        {
                            "id": 101,
                            "tag_name": "v0.1.1",
                            "draft": False,
                            "prerelease": False,
                            "assets": [{"id": 201, "name": new.name}],
                        }
                    ]
                )
            )
            settings = root / "settings"
            settings.mkdir()
            (settings / "state.json").write_text(
                json.dumps(
                    {
                        "sources": {"Unrelated Plugin": "owner/repo"},
                        "hardware_test_marker": "preserve-me",
                    }
                )
            )
            script = r"""
import asyncio, importlib.util, json, pathlib, sys, types
root = pathlib.Path(sys.argv[1])
plugin = root / 'plugins/decky-direct-updater'
# Loader has its own top-level updater module alias; ours must not collide.
sys.modules['updater'] = types.ModuleType('updater')
sys.modules['decky'] = types.SimpleNamespace(
    DECKY_PLUGIN_DIR=str(plugin), DECKY_PLUGIN_SETTINGS_DIR=str(root / 'settings'),
    DECKY_PLUGIN_RUNTIME_DIR=str(root / 'runtime'), logger=types.SimpleNamespace(error=print))
spec = importlib.util.spec_from_file_location('tested_plugin', plugin / 'main.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
async def run():
    app = module.Plugin()
    await app._main()
    before = await app.list_plugins()
    assert before[0]['version'] == '0.1.0', before
    app.updater.github.official_sources = lambda: {}
    checked = await app.check_updates()
    assert checked[0]['status'] == 'update', checked
    response = await app.stage_update('decky-direct-updater', 101, 201)
    assert not response['error'], response
    staged = response['update']
    assert staged['version'] == '0.1.1'
    assert pathlib.Path(staged['artifact'][7:]).exists()
    assert len(staged['hash']) == 64
    # A staged request must not itself mutate the installed plugin.
    assert (await app.list_plugins())[0]['version'] == '0.1.0'
    app.updater.state.put('sources', 'Another Plugin', 'another/repo')
    state = json.loads((root / 'settings/state.json').read_text())
    assert state['hardware_test_marker'] == 'preserve-me'
    assert state['sources']['Unrelated Plugin'] == 'owner/repo'
asyncio.run(run())
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(root)], capture_output=True, text=True, cwd=root
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
