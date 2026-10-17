import asyncio
import importlib.util
import ssl
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from direct_updater.github_releases import GitHub, GitHubError
from direct_updater.tls import github_ssl_context


class TLS(unittest.TestCase):
    def test_adds_deckys_bundled_ca_to_default_verified_context(self):
        context = Mock()
        bundle = types.SimpleNamespace(where=lambda: "/bundled/certifi/cacert.pem")
        with (
            patch("ssl.create_default_context", return_value=context) as default,
            patch.dict(sys.modules, {"certifi": bundle}),
        ):
            self.assertIs(github_ssl_context(), context)
        default.assert_called_once_with()
        context.load_verify_locations.assert_called_once_with(cafile="/bundled/certifi/cacert.pem")

    def test_standard_python_retains_verification_without_certifi(self):
        with patch.dict(sys.modules, {"certifi": None}):
            context = github_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_api_opener_receives_verified_context(self):
        context = ssl.create_default_context()
        with (
            patch("direct_updater.github_releases.github_ssl_context", return_value=context),
            patch("urllib.request.HTTPSHandler") as handler,
            patch("urllib.request.build_opener"),
        ):
            GitHub(Mock())
        handler.assert_called_once_with(context=context)

    def test_tls_error_is_actionable_and_original_reason_is_logged(self):
        state = Mock()
        state.get.return_value = None
        client = GitHub(state)
        client.opener = Mock()
        client.opener.open.side_effect = urllib.error.URLError(
            ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED")
        )
        with self.assertLogs("direct_updater.github_releases", level="WARNING") as logs:
            with self.assertRaisesRegex(GitHubError, "TLS certificate"):
                client.get("/repos/owner/repo/releases")
        self.assertIn("CERTIFICATE_VERIFY_FAILED", logs.output[0])

    def test_source_search_returns_expected_errors_without_rpc_exception(self):
        spec = importlib.util.spec_from_file_location(
            "rpc_entrypoint", Path(__file__).resolve().parents[1] / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"decky": types.ModuleType("decky")}):
            spec.loader.exec_module(module)
        plugin = module.Plugin()
        plugin.updater = Mock()
        plugin.updater.search.side_effect = GitHubError("GitHub rate limit reached; retry later")
        result = asyncio.run(plugin.search_source("unknown-plugin"))
        self.assertEqual(
            result, {"candidates": [], "error": "GitHub rate limit reached; retry later"}
        )


class StageErrors(unittest.TestCase):
    def test_preparation_failure_returns_message_without_rpc_exception(self):
        spec = importlib.util.spec_from_file_location(
            "stage_rpc", Path(__file__).resolve().parents[1] / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"decky": types.ModuleType("decky")}):
            spec.loader.exec_module(module)
        plugin = module.Plugin()
        plugin.updater = Mock()
        plugin.updater.stage.side_effect = GitHubError("GitHub rate limit reached; retry in 2 min")
        result = asyncio.run(plugin.stage_update("TabMaster", "v2.16.2", "TabMaster.zip"))
        self.assertIsNone(result["update"])
        self.assertIn("retry in 2 min", result["error"])


class SourceConfirmationErrors(unittest.TestCase):
    def test_stale_candidate_returns_a_readable_error_instead_of_rpc_exception(self):
        spec = importlib.util.spec_from_file_location(
            "confirm_rpc", Path(__file__).resolve().parents[1] / "main.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"decky": types.ModuleType("decky")}):
            spec.loader.exec_module(module)
        plugin = module.Plugin()
        plugin.updater = Mock()
        plugin.updater.confirm.side_effect = ValueError(
            "Choose a source from this plugin's verified suggestions"
        )
        result = asyncio.run(plugin.confirm_source("plugin", "other/repo"))
        self.assertFalse(result["success"])
        self.assertIn("verified suggestions", result["error"])
