"""Check packaged defaults and explicit session-retention overrides."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LauncherTests(unittest.TestCase):
    def launch(self, *arguments):
        with tempfile.TemporaryDirectory() as scratch:
            wrapper = Path(scratch) / "zypak-wrapper"
            wrapper.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            wrapper.chmod(0o755)
            result = subprocess.run(
                ["sh", str(ROOT / "launcher/teams-office"), *arguments],
                env=dict(os.environ, PATH=scratch + ":" + os.environ["PATH"],
                         XDG_RUNTIME_DIR=scratch, FLATPAK_ID="eu.nosini.TeamsOffice"),
                check=True, capture_output=True, text=True,
            )
            return json.loads(result.stdout)

    def test_enables_document_session_retention_and_office_bridge(self):
        arguments = self.launch()
        self.assertEqual(arguments[0], "/app/teams-office/teams-for-linux")
        for flag in ("--mcp.enabled", "--mcp.addin.enabled", "--mcp.documentSession.enabled"):
            self.assertEqual(arguments.count(flag), 1)

    def test_explicit_retention_override_does_not_receive_a_duplicate_default(self):
        for override in ("--mcp.documentSession.enabled=false", "--mcp.documentSession.enabled=true",
                         "--mcp.documentSession.enabled", "--no-mcp.documentSession.enabled"):
            with self.subTest(override=override):
                arguments = self.launch(override, "--mcp.documentSession.days=3")
                self.assertEqual(arguments[-2:], [override, "--mcp.documentSession.days=3"])
                self.assertEqual(arguments.count("--mcp.documentSession.enabled"), int(override == "--mcp.documentSession.enabled"))


if __name__ == "__main__":
    unittest.main()
