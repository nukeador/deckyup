"""Security facts come from the selected archive; no network or execution."""

import hashlib
import json
from unittest.mock import Mock, patch

from direct_updater.installed_plugins import installed_plugins
from direct_updater.package_validation import validate_package
from direct_updater.security import assess_security, security_facts
from test_updater import Workspace, NAME, archive_bytes, release


def binary(name="helper", host="downloads.example.org", digest="a" * 64):
    return {
        "name": name,
        "url": f"https://{host}/v1/helper?token=do-not-display",
        "sha256hash": digest,
    }


def facts(root=False, binaries=None, backend=False):
    return security_facts(
        {"flags": ["root"] if root else []}, {"remote_binary": binaries or []}, backend
    )


class SecurityPolicy(Workspace):
    def test_exact_root_flag_and_backend_in_validated_zip(self):
        path = self.root / "plugin.zip"
        for flags, expected in (
            ([], False),
            (["_root", "rooted", "Root"], False),
            (["root"], True),
        ):
            path.write_bytes(
                archive_bytes(
                    extra={
                        "plugin/plugin.json": json.dumps({"name": NAME, "flags": flags}),
                        "plugin/main.py": "# never executed",
                    }
                )
            )
            security = validate_package(path, NAME, "0.1.1")["security"]
            self.assertEqual(security["root_requested"], expected)
            self.assertTrue(security["has_python_backend"])
            self.assertEqual(security["flags"], flags)
        path.write_bytes(archive_bytes(extra={"plugin/nested/main.py": "# not a backend"}))
        self.assertFalse(validate_package(path, NAME, "0.1.1")["security"]["has_python_backend"])

    def test_binary_facts_and_redacted_assessment(self):
        path = self.root / "plugin.zip"
        path.write_bytes(
            archive_bytes(
                extra={
                    "plugin/package.json": json.dumps(
                        {"version": "0.1.1", "remote_binary": [binary()]}
                    )
                }
            )
        )
        security = validate_package(path, NAME, "0.1.1")["security"]
        self.assertEqual(security["external_binaries"][0]["source_url"], binary()["url"])
        self.assertEqual(security["external_binaries"][0]["declared_hash"], "a" * 64)
        assessment = assess_security(security)
        self.assertTrue(assessment["requires_acknowledgment"])
        self.assertNotIn("do-not-display", json.dumps(assessment))
        self.assertEqual(assessment["external_binaries"][0]["source_host"], "downloads.example.org")

    def test_policy_matrix(self):
        cases = [
            (facts(), None, False, False, None),
            (facts(backend=True), None, False, False, None),
            (facts(True), None, False, True, "root_requested"),
            (facts(True), facts(), True, True, "root_added"),
            (facts(True), facts(True), True, False, "root_requested"),
            (facts(), facts(True), True, False, None),
            (facts(binaries=[binary()]), facts(), True, True, "external_binaries_added"),
            (
                facts(binaries=[binary(host="other.example.org")]),
                facts(binaries=[binary()]),
                True,
                True,
                "external_binary_origin_changed",
            ),
            (
                facts(binaries=[binary(digest="b" * 64)]),
                facts(binaries=[binary()]),
                True,
                False,
                None,
            ),
            (facts(True), None, True, True, "comparison_unavailable"),
            (facts(binaries=[binary()]), None, True, True, "comparison_unavailable"),
            (facts(), None, True, False, "comparison_unavailable"),
        ]
        for current, previous, updating, required, finding in cases:
            with self.subTest(current=current, previous=previous):
                result = assess_security(current, previous, updating)
                self.assertEqual(result["requires_acknowledgment"], required)
                if finding:
                    self.assertIn(finding, [f["kind"] for f in result["findings"]])
                if previous is None:
                    self.assertIsNone(result["previous_root_requested"])

    def test_same_name_new_host_and_new_binary_are_not_hidden_by_existing_root(self):
        previous = facts(True, [binary()])
        current = facts(True, [binary(host="new.example.org"), binary(name="second")])
        result = assess_security(current, previous, True)
        self.assertTrue(result["requires_acknowledgment"])
        self.assertEqual(result["added_binary_names"], ["second"])
        self.assertEqual(result["changed_binary_source_hosts"], ["helper"])

    def test_malformed_security_metadata_fails_closed(self):
        for manifest, package in [
            ({"flags": "root"}, {}),
            ({"flags": None}, {}),
            ({"flags": [1]}, {}),
            ({}, {"remote_binary": None}),
            ({}, {"remote_binary": {}}),
            ({}, {"remote_binary": [{}]}),
            ({}, {"remote_binary": [binary(), binary()]}),
            ({}, {"remote_binary": [{**binary(), "url": "file:///tmp/secret"}]}),
            ({}, {"remote_binary": [{**binary(), "url": "https://user:pass@example.org/file"}]}),
            ({}, {"remote_binary": [{**binary(), "sha256hash": 12}]}),
        ]:
            with (
                self.subTest(manifest=manifest, package=package),
                self.assertRaisesRegex(ValueError, "Could not inspect"),
            ):
                security_facts(manifest, package, False)
        # Omitted optional declarations match Loader semantics, not unreadable manifests.
        self.assertFalse(security_facts({}, {}, False)["root_requested"])

    def test_missing_and_unreadable_installed_metadata_is_unknown(self):
        folder = self.install()
        (folder / "package.json").unlink()
        self.assertIsNone(installed_plugins(self.root / "plugins")[0]["security"])
        (folder / "package.json").write_text("{")
        self.assertIsNone(installed_plugins(self.root / "plugins")[0]["security"])
        with patch("direct_updater.installed_plugins.read_json", side_effect=PermissionError()):
            self.assertIsNone(installed_plugins(self.root / "plugins")[0]["security"])

    def test_invalid_identity_and_corrupt_zip_still_rejected(self):
        path = self.root / "bad.zip"
        for content in (
            archive_bytes(name="Impostor"),
            b"not a zip",
            archive_bytes(missing="plugin/package.json"),
        ):
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                validate_package(path, NAME, "0.1.1")


class SecurityStaging(Workspace):
    def setUp(self):
        super().setUp()
        self.folder = self.install()
        self.app = self.updater()

    def stage(self, root=True):
        staged = self.staged_package(
            extra={
                "plugin/plugin.json": json.dumps({"name": NAME, "flags": ["root"] if root else []})
            }
        )
        return self.app.security.register(staged, updating=True)

    def test_review_bound_to_checksum_and_single_use(self):
        staged = self.stage()
        with self.assertRaisesRegex(ValueError, "Review plugin"):
            self.app.authorize_staged(staged["review_token"], False)
        for truthy in ("true", 1):
            with self.assertRaises(ValueError):
                self.app.authorize_staged(staged["review_token"], truthy)
        result = self.app.authorize_staged(staged["review_token"], True)
        self.assertTrue(result["security_authorized"])
        self.assertEqual(result["hash"], staged["hash"])
        with self.assertRaises(ValueError):
            self.app.authorize_staged(staged["review_token"], True)

    def test_changed_archive_requires_fresh_assessment(self):
        staged = self.stage()
        path = self.app.staging / "update-test.zip"
        path.write_bytes(archive_bytes())
        with self.assertRaisesRegex(ValueError, "changed"):
            self.app.authorize_staged(staged["review_token"], True)
        self.assertFalse(path.exists())

    def test_changed_installed_flags_or_version_invalidates_acknowledgment(self):
        for metadata, value in [
            ("plugin.json", {"name": NAME, "flags": ["root"]}),
            ("package.json", {"name": "decky-direct-updater", "version": "0.2.0"}),
        ]:
            staged = self.stage()
            path = self.folder / metadata
            original = path.read_text()
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "changed"):
                self.app.authorize_staged(staged["review_token"], True)
            path.write_text(original)

    def test_cancel_removes_archive_and_invalidates_review(self):
        staged = self.stage()
        self.app.discard_staged(staged["review_token"])
        self.assertFalse((self.app.staging / "update-test.zip").exists())
        with self.assertRaises(ValueError):
            self.app.authorize_staged(staged["review_token"], True)

    def test_expiry_and_symlink_cannot_be_approved(self):
        for change in ("expired", "symlink"):
            staged = self.stage()
            record = self.app.security.pending[staged["review_token"]]
            if change == "expired":
                record["time"] -= 1801
            else:
                record["path"].unlink()
                record["path"].symlink_to(self.folder / "package.json")
            with self.assertRaises(ValueError):
                self.app.authorize_staged(staged["review_token"], True)
            self.assertTrue((self.folder / "package.json").exists())

    def test_unknown_installed_flags_requires_review_for_root(self):
        (self.folder / "plugin.json").write_text(json.dumps({"name": NAME, "flags": "bad"}))
        staged = self.stage()
        self.assertFalse(staged["security"]["comparison_available"])
        self.assertTrue(staged["security"]["requires_acknowledgment"])

    def test_metadata_from_repository_cannot_override_archive_flags(self):
        staged = self.staged_package(
            extra={"plugin/plugin.json": json.dumps({"name": NAME, "flags": ["root"]})}
        )
        self.app.github.releases = Mock(return_value=[release()])
        with patch("direct_updater.plugin_updates.stage_download", return_value=staged) as download:
            result = self.app.stage("updater", 10, 20)
        download.assert_called_once()
        self.assertTrue(result["security"]["root_requested"])
        self.assertEqual(result["previous_version"], "0.1.0")
        self.assertNotIn("security_facts", result)
        self.assertEqual(
            result["hash"],
            hashlib.sha256((self.app.staging / "update-test.zip").read_bytes()).hexdigest(),
        )

    def test_real_download_repack_and_review_share_one_artifact(self):
        from pathlib import Path

        content = archive_bytes(
            extra={
                "plugin/plugin.json": json.dumps({"name": NAME, "flags": ["root"]}),
                "plugin/package.json": json.dumps(
                    {"name": "decky-direct-updater", "version": "0.1.1"}
                ),
            }
        )
        entry = release()
        asset = entry["assets"][0]
        asset.update(size=len(content), digest="sha256:" + hashlib.sha256(content).hexdigest())
        response = Mock()
        response.headers = {"Content-Length": str(len(content))}
        response.geturl.return_value = asset["browser_download_url"]
        response.read.side_effect = [content, b""]
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        self.app.github.releases = Mock(return_value=[entry])
        with patch("urllib.request.build_opener", return_value=opener):
            staged = self.app.stage("updater", 10, 20)
        opener.open.assert_called_once()
        path = Path(staged["artifact"][7:])
        checked = validate_package(
            path,
            NAME,
            "0.1.1",
            expected_root="updater",
            expected_package_name="decky-direct-updater",
        )
        self.assertTrue(checked["security"]["root_requested"])
        self.assertTrue(staged["security"]["requires_acknowledgment"])
        authorized = self.app.authorize_staged(staged["review_token"], True)
        self.assertEqual(authorized["hash"], hashlib.sha256(path.read_bytes()).hexdigest())
