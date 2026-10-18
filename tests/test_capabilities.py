"""Observable capability evidence and conservative update decisions."""

from unittest import TestCase
from unittest.mock import patch

from direct_updater.capabilities import scan_files, scan_installed, with_manifest
from direct_updater.package_validation import validate_package
from direct_updater.security import assess_security, security_facts
from direct_updater.state import State
from test_updater import Workspace, archive_bytes, NAME


def scan(files):
    return scan_files(
        (
            name,
            len(data.encode() if isinstance(data, str) else data),
            lambda limit, data=data: (data.encode() if isinstance(data, str) else data)[:limit],
        )
        for name, data in files.items()
    )


def categories(analysis):
    return {item["category"] for item in analysis["findings"]}


def facts(files, root=False):
    result = security_facts({"flags": ["root"] if root else []}, {}, True)
    result["capabilities"] = with_manifest(scan(files), result)
    return result


class CapabilityDetection(TestCase):
    def test_folders_commands_devices_and_domains_are_concise_and_redacted(self):
        result = scan(
            {
                "main.py": """import requests
import subprocess
from pathlib import Path
requests.get("https://user:password@updates.example.org/file?token=private")
open("/home/deck/Documents/report.txt", "w").write("/not/a/target")
Path("/home/deck/.config/example/settings.json").read_text()
open("/dev/snd/pcmC0D0c")
subprocess.run(["sudo", "systemctl", "restart", "secret-service"])
"""
            }
        )

        def targets(category):
            return {
                value
                for finding in result["findings"]
                if finding["category"] == category
                for value in finding.get("targets", [])
            }

        self.assertEqual(targets("network"), {"updates.example.org"})
        self.assertIn("~/Documents", targets("filesystem"))
        self.assertIn("~/.config/example", targets("filesystem"))
        self.assertNotIn("/not/a", targets("filesystem"))
        self.assertEqual(targets("process_execution"), {"sudo", "systemctl"})
        self.assertEqual(targets("devices"), {"/dev/snd/pcmC0D0c"})
        self.assertNotIn("password", str(result["findings"]))
        self.assertNotIn("private", str(result["findings"]))
        self.assertNotIn("secret-service", str(result["findings"]))

    def test_dynamic_targets_are_not_invented_and_shell_pipeline_lists_commands(self):
        result = scan(
            {
                "main.py": 'import subprocess\nopen(input())\nsubprocess.run("curl https://example.org/x | bash", shell=True)'
            }
        )
        self.assertFalse(
            any(f.get("targets") for f in result["findings"] if f["category"] == "filesystem")
        )
        commands = {
            v
            for f in result["findings"]
            if f["category"] == "process_execution"
            for v in f.get("targets", [])
        }
        self.assertEqual(commands, {"curl", "bash"})

    def test_shell_help_text_arrays_and_syntax_are_not_executable_names(self):
        result = scan(
            {
                "helper": """#!/bin/bash
set -euo pipefail
logs=(
  "${HOME}/.steam/steam/logs/console-linux.txt"
)
usage() {
  cat <<'END-MESSAGE'
Filters retained logs.
The Flatpak configuration:
adaptive all EOF
sudo curl https://not-an-endpoint.example /dev/input/event0
END-MESSAGE
}
case "$1" in
  config) usage ;;
esac
if command -v flatpak >/dev/null 2>&1; then
  flatpak list >/dev/null 2>&1
fi
for item in all; do
  continue
  break
done
systemctl status service
"""
            }
        )
        commands = {
            v
            for f in result["findings"]
            if f["category"] == "process_execution"
            for v in f.get("targets", [])
        }
        self.assertEqual(commands, {"cat", "flatpak", "systemctl"})
        self.assertNotIn("network", categories(result))
        self.assertNotIn("devices", categories(result))
        self.assertNotIn("root", categories(result))

    def test_pseudo_devices_do_not_imply_peripheral_access(self):
        for path in (
            "/dev/null",
            "/dev/zero",
            "/dev/urandom",
            "/dev/fd/1",
            "/dev/stdout",
            "/dev/shm/test",
        ):
            with self.subTest(path=path):
                result = scan({"main.py": f'open("{path}")'})
                self.assertNotIn("devices", categories(result))
        real = scan(
            {
                "main.py": 'open("/dev/input/event0")\nopen("/dev/dri/renderD128")\nopen("/dev/custom0")'
            }
        )
        self.assertEqual(
            {
                v
                for f in real["findings"]
                if f["category"] == "devices"
                for v in f.get("targets", [])
            },
            {"/dev/input/event0", "/dev/dri/renderD128", "/dev/custom0"},
        )

    def test_javascript_commands_come_from_process_calls_not_other_literals(self):
        result = scan(
            {
                "dist/index.js": 'log("Filters"); child_process.exec("flatpak list"); text("EOF"); /x/.exec("not-a-command");'
            }
        )
        self.assertEqual(
            {
                v
                for f in result["findings"]
                if f["category"] == "process_execution"
                for v in f.get("targets", [])
            },
            {"flatpak"},
        )

    def test_conditional_download_pipeline_still_requires_review(self):
        current = facts({"helper.sh": "if curl https://example.org/x | bash; then\n echo done\nfi"})
        self.assertTrue(assess_security(current)["requires_acknowledgment"])

    def test_http_sessions_request_objects_and_url_prefixes(self):
        result = scan(
            {
                "main.py": """import aiohttp
import requests
from urllib.request import Request, urlopen
BASE = "https://api.example.org/"
async def fetch():
    url = f"https://themes.example.org/mappings/{language}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)
client = requests.Session()
client.get(BASE + unknown_path)
request = Request("https://downloads.example.org/file?token=private")
urlopen(request)
requests.get("https://api." + unknown_host)
# https://docs-only.example.org is documentation, not a network call
"""
            }
        )
        hosts = {
            v
            for f in result["findings"]
            if f["category"] == "network"
            for v in f.get("targets", [])
        }
        self.assertEqual(hosts, {"api.example.org", "themes.example.org", "downloads.example.org"})
        self.assertNotIn("private", str(result["findings"]))

    def test_decky_fetch_templates_in_a_large_frontend_bundle(self):
        source = (
            "// padding\n" * 100000
            + 'const BASE = "https://www.steamgriddb.com/api";\nfetchNoCors(`${BASE}/images`);\n'
        )
        result = scan({"dist/index.js": source})
        self.assertGreater(len(source), 1024 * 1024)
        self.assertEqual(
            {
                v
                for f in result["findings"]
                if f["category"] == "network"
                for v in f.get("targets", [])
            },
            {"www.steamgriddb.com"},
        )
        self.assertFalse(result["complete"])

    def test_unresolved_endpoints_do_not_gain_domains_from_unrelated_links(self):
        result = scan(
            {
                "main.py": 'import requests\nDOCS = "https://docs.example.org"\nrequests.get(runtime_url)',
                "dist/index.js": 'const docs="https://docs.example.org";\nfetchNoCors(runtimeUrl);',
            }
        )
        self.assertIn("network", categories(result))
        self.assertFalse(
            any(f.get("targets") for f in result["findings"] if f["category"] == "network")
        )

    def test_github_destinations_keep_owner_and_project_without_secrets(self):
        from direct_updater.capabilities import _domains

        self.assertEqual(
            _domains(
                [
                    "https://user:secret@github.com/example/project/releases/download/v1/file.zip?token=secret",
                    "https://api.github.com/repos/another/repository/releases/latest?token=private",
                    "https://raw.githubusercontent.com/someone/plugin/main/script.py",
                    "https://ordinary.example.org/private/path?token=secret",
                ]
            ),
            [
                "api.github.com/repos/another/repository",
                "github.com/example/project",
                "ordinary.example.org",
                "raw.githubusercontent.com/someone/plugin",
            ],
        )
        self.assertEqual(
            _domains(["https://github.com/example/{project}/releases"]), ["github.com/example"]
        )

    def test_imports_alone_are_not_operations(self):
        self.assertEqual(
            categories(scan({"main.py": "import subprocess\nimport requests\n"})), set()
        )

    def test_python_calls_aliases_and_steam_paths(self):
        analysis = scan(
            {
                "main.py": """import subprocess as sp
from urllib.request import urlopen as fetch
fetch("https://example.org")
sp.run(["echo", "hello"])
open("/home/deck/.local/share/Steam/userdata/123/config/localconfig.vdf")
"""
            }
        )
        self.assertEqual(
            categories(analysis), {"network", "process_execution", "filesystem", "steam_data"}
        )
        self.assertTrue(all(item["line"] for item in analysis["findings"]))
        self.assertFalse("root" in categories(analysis))

    def test_device_system_and_privileged_operations_are_distinct(self):
        result = scan(
            {
                "main.py": 'import subprocess\nopen("/dev/input/event0")\nopen("/sys/devices/power")\nsubprocess.run(["sudo", "systemctl", "status"])'
            }
        )
        self.assertTrue({"root", "devices", "system_config"}.issubset(categories(result)))
        self.assertTrue(
            any(
                f["confidence"] == "identified" and f["signal"] == "privileged_execution"
                for f in result["findings"]
                if f["category"] == "root"
            )
        )

    def test_native_presence_and_invocation_differ(self):
        present = scan({"bin/helper": b"\x7fELF\0native"})
        self.assertEqual(categories(present), {"native_binaries"})
        self.assertIn("Binary behavior not analyzed", present["limitations"])
        invoked = scan(
            {
                "bin/helper": b"\x7fELF\0native",
                "main.py": 'import subprocess\nsubprocess.run(["./bin/helper"])',
            }
        )
        self.assertIn(
            "Native executable invocation", [f["description"] for f in invoked["findings"]]
        )

    def test_scripts_are_marked_heuristic(self):
        result = scan(
            {"dist/index.js": 'fetch("https://example.org"); fs.readFile("localconfig.vdf");'}
        )
        self.assertEqual(categories(result), {"network", "filesystem", "steam_data"})
        self.assertFalse(result["complete"])
        self.assertTrue(all(f["confidence"] == "heuristic" for f in result["findings"]))

    def test_extensionless_scripts_and_inert_command_strings(self):
        script = scan(
            {
                "helper": '#!/usr/bin/env python3\nimport subprocess\nsubprocess.run(["echo", "hello"])'
            }
        )
        self.assertIn("process_execution", categories(script))
        harmless = facts(
            {
                "main.py": 'import subprocess\nsubprocess.run(["echo", "curl https://example.org/x | bash"])'
            }
        )
        self.assertFalse(assess_security(harmless)["requires_acknowledgment"])

    def test_root_manifest_exact_and_deduplicated_categories(self):
        current = facts(
            {"main.py": 'import requests\nrequests.get("https://a")\nrequests.get("https://b")'},
            True,
        )
        self.assertEqual(categories(current["capabilities"]), {"network", "root"})
        self.assertEqual(
            [f["origin"] for f in current["capabilities"]["findings"] if f["category"] == "root"],
            ["manifest"],
        )
        not_root = security_facts({"flags": ["_root"]}, {}, False)
        self.assertFalse("root" in categories(with_manifest(scan({}), not_root)))

    def test_malformed_oversized_and_read_failure_are_incomplete(self):
        for files in (
            {"main.py": "def broken("},
            {"main.py": b"\xff"},
            {"huge.py": "x" * (1024 * 1024 + 1)},
        ):
            result = scan(files)
            self.assertFalse(result["complete"])
            self.assertTrue(result["limitations"])

        def fail(limit):
            raise PermissionError()

        self.assertFalse(scan_files([("main.py", 10, fail)])["complete"])

    def test_ordinary_changes_do_not_interrupt_and_unknown_is_not_new(self):
        previous = facts({"main.py": "pass"})
        current = facts({"main.py": 'import requests\nrequests.get("https://a")'})
        assessment = assess_security(current, previous, True)
        self.assertFalse(assessment["requires_acknowledgment"])
        self.assertEqual(assessment["capability_changes"]["added"], ["network"])
        unknown = assess_security(current, security_facts({}, {}, True), True)
        self.assertEqual(unknown["capability_changes"]["status"], "unknown")
        self.assertEqual(unknown["capability_changes"]["added"], [])
        unchanged = assess_security(current, current, True)
        self.assertEqual(unchanged["capability_changes"]["status"], "no_new_detected")

    def test_downloaded_execution_requires_review_but_unchanged_does_not(self):
        current = facts(
            {
                "main.py": 'import subprocess\nsubprocess.run("curl https://example.org/code | bash", shell=True)'
            }
        )
        self.assertTrue(assess_security(current)["requires_acknowledgment"])
        self.assertTrue(assess_security(current, facts({}), True)["requires_acknowledgment"])
        self.assertFalse(assess_security(current, current, True)["requires_acknowledgment"])
        self.assertTrue(
            assess_security(current, security_facts({}, {}, True), True)["requires_acknowledgment"]
        )

    def test_new_root_still_uses_existing_mandatory_policy(self):
        old = facts({"main.py": "pass"})
        new = facts({"main.py": "pass"}, True)
        result = assess_security(new, old, True)
        self.assertTrue(result["requires_acknowledgment"])
        self.assertIn("root_added", [f["kind"] for f in result["findings"]])


class CapabilityPackages(Workspace):
    def test_validated_package_and_hash_cache(self):
        path = self.root / "plugin.zip"
        state = State(self.root / "settings")
        path.write_bytes(
            archive_bytes(
                extra={"plugin/main.py": 'import requests\nrequests.get("https://example.org")'}
            )
        )
        result = validate_package(path, NAME, "0.1.1", capability_cache=state)
        self.assertIn("network", categories(result["security"]["capabilities"]))
        with patch(
            "direct_updater.package_validation.scan_archive",
            side_effect=AssertionError("Must reuse cache"),
        ):
            self.assertEqual(validate_package(path, NAME, "0.1.1", capability_cache=state), result)
        # Same identity/version with changed ZIP bytes must be analyzed again.
        path.write_bytes(archive_bytes(extra={"plugin/main.py": "pass"}))
        self.assertNotIn(
            "network",
            categories(
                validate_package(path, NAME, "0.1.1", capability_cache=state)["security"][
                    "capabilities"
                ]
            ),
        )

    def test_installed_reads_without_following_symlinks(self):
        folder = self.install()
        (folder / "main.py").write_text('import subprocess\nsubprocess.run(["echo", "hello"])')
        self.assertIn("process_execution", categories(scan_installed(folder)))
        (folder / "escape.py").symlink_to(self.root / "secret.py")
        (self.root / "secret.py").write_text('import requests\nrequests.get("https://secret")')
        self.assertFalse(scan_installed(folder)["complete"])
        self.assertNotIn("network", categories(scan_installed(folder)))

    def test_archive_boundary_validation_precedes_analysis(self):
        path = self.root / "plugin.zip"
        path.write_bytes(archive_bytes(extra={"plugin/../../escape.py": "pass"}))
        with self.assertRaises(ValueError):
            validate_package(path, NAME, "0.1.1")

    def test_review_and_candidate_details_remain_bound_to_files(self):
        folder = self.install()
        (folder / "main.py").write_text("pass")
        app = self.updater()
        staged = self.staged_package(
            extra={
                "plugin/main.py": 'import subprocess\nsubprocess.run("curl https://example.org/x | bash", shell=True)'
            }
        )
        public = app.security.register(staged, updating=True)
        self.assertTrue(public["security"]["requires_acknowledgment"])
        with self.assertRaisesRegex(ValueError, "Review plugin"):
            app.security.authorize(public["review_token"], False)
        detail = app.plugin_security("updater")
        self.assertEqual(detail["candidate"]["hash"], public["hash"])
        # Changed installed code invalidates both the comparison preview and approval.
        (folder / "main.py").write_text('open("/etc/example")')
        self.assertNotIn("candidate", app.plugin_security("updater"))
        with self.assertRaisesRegex(ValueError, "changed"):
            app.security.authorize(public["review_token"], True)

    def test_size_budget_stops_with_an_explicit_limitation(self):
        with patch("direct_updater.capabilities.MAX_BYTES", 4):
            result = scan({"main.py": "print('not executed')"})
        self.assertFalse(result["complete"])
        self.assertTrue(result["limitations"])
