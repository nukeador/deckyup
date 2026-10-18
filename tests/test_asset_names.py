import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from direct_updater.package_validation import stage_download
from test_updater import archive_bytes

from direct_updater.github_releases import compatible_releases


class StableAssetNames(unittest.TestCase):
    plugin = {"name": "ResonaDeck", "package_name": "resonadeck"}

    def release(self, *names, tag="1.2.0", prerelease=False):
        return {
            "id": 1,
            "tag_name": tag,
            "prerelease": prerelease,
            "assets": [{"id": i, "name": name} for i, name in enumerate(names)],
        }

    def test_stable_channel_filename_matches_stable_tag(self):
        for label in (
            "Stable",
            "stable",
            "STABLE",
            "Final",
            "release",
            "SteamDeck",
            "PortableBuild",
            "Stable.1",
        ):
            with self.subTest(label=label):
                choices, ambiguous = compatible_releases(
                    self.plugin, [self.release(f"ResonaDeck-1.2.0-{label}.zip")]
                )
                self.assertFalse(ambiguous)
                self.assertEqual(len(choices), 1)
                self.assertEqual(choices[0][0].text, "1.2.0")

    def test_other_versions_channels_and_identities_remain_rejected(self):
        for name in (
            "ResonaDeck-1.2.1-Stable.zip",
            "ResonaDeck-1.2.0-beta.zip",
            "Other-1.2.0-Stable.zip",
            "ResonaDeck-source-1.2.0-Stable.zip",
            "ResonaDeck-1.2.0-source.zip",
            "ResonaDeck-1.2.0-Linux-beta.zip",
            "ResonaDeck-1.2.0-RC1.zip",
            "ResonaDeck-1.2.0_beta.zip",
            "ResonaDeck-1.2.0 Preview.zip",
            "ResonaDeck-1.2.0_steamdeck-nightly.zip",
            "ResonaDeck-1.3-Final.zip",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    compatible_releases(self.plugin, [self.release(name)]), ([], False)
                )

    def test_stable_label_does_not_resolve_ambiguous_assets(self):
        self.assertEqual(
            compatible_releases(
                self.plugin,
                [self.release("ResonaDeck-1.2.0.zip", "ResonaDeck-1.2.0-Stable.zip")],
            ),
            ([], True),
        )

    def test_actual_prereleases_stay_out_of_automatic_updates(self):
        for entry in (
            self.release("ResonaDeck-1.2.0-Stable.zip", prerelease=True),
            self.release("ResonaDeck-1.2.0-Stable.zip", tag="1.2.0-Stable"),
        ):
            self.assertEqual(compatible_releases(self.plugin, [entry]), ([], False))

    def test_manual_prerelease_selection_remains_explicit(self):
        entry = self.release("ResonaDeck-1.3.0-rc.1.zip", tag="1.3.0-rc.1", prerelease=True)
        self.assertEqual(compatible_releases(self.plugin, [entry]), ([], False))
        self.assertEqual(
            len(compatible_releases(self.plugin, [entry], allow_prerelease=True)[0]), 1
        )

    def test_packaging_label_separators_are_not_semver_prereleases(self):
        for separator in ("-", "_", " "):
            entry = self.release(f"ResonaDeck-1.2.0{separator}CustomPackaging.zip")
            self.assertEqual(len(compatible_releases(self.plugin, [entry])[0]), 1)

    def test_unknown_suffix_cannot_hide_prerelease_inside_zip(self):
        entry = self.release("ResonaDeck-1.2.0-CustomPackaging.zip")
        self.assertEqual(len(compatible_releases(self.plugin, [entry])[0]), 1)
        url = "https://github.com/ValentineBSAA/ResonaDeck/releases/download/1.2.0/ResonaDeck-1.2.0-CustomPackaging.zip"
        for version in ("1.2.0-beta.1", "1.2.0-mystery.1", "1.3.0"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                data = archive_bytes(name="ResonaDeck", version=version)
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.geturl.return_value = url
                response.headers = {"Content-Length": str(len(data))}
                response.read.side_effect = [data, b""]
                with patch("urllib.request.build_opener") as opener:
                    opener.return_value.open.return_value = response
                    with self.assertRaisesRegex(ValueError, "ZIP version does not match"):
                        stage_download(
                            {"browser_download_url": url, "size": len(data)},
                            "ValentineBSAA/ResonaDeck",
                            "ResonaDeck",
                            "1.2.0",
                            tmp,
                        )
                self.assertEqual(list(Path(tmp).glob("update-*.zip")), [])
