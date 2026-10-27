#!/usr/bin/env python3
"""Exercise the workflow's tag classification and release commands offline."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/flatpak.yml").read_text())


class ReleaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)
        self.env = dict(os.environ, APP_NAME="Example", TAG="v1.2.3")

    def run_step(self, job, name, **env):
        step = next(step for step in WORKFLOW["jobs"][job]["steps"]
                    if step.get("name") == name)
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=self.directory, env=dict(self.env, **env),
            capture_output=True, text=True,
        )

    def test_tag_classification(self):
        for tag, stable in (
            ("v1.32.16", True), ("v1.32.16-1", True),
            ("v1.32.16-12", True), ("v1.32.17-rc1", False),
            ("v1.32.17-beta.2", False), ("v1.32.17rc1", False),
            ("v1.32.16-", False), ("v1.32.16-1rc1", False),
        ):
            with self.subTest(tag=tag):
                output = self.directory / "output"
                result = self.run_step(
                    "setup", "Classify the release tag",
                    TAG=tag, GITHUB_OUTPUT=str(output),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(), f"stable={str(stable).lower()}\n")
                output.unlink()

    def release_commands(self, *, stable="true", exists="false", fail="false", assets=True):
        bundles = self.directory / "bundles"
        bundles.mkdir()
        for name in ("example-x86_64.flatpak", "example-addon-x86_64.flatpak"):
            if assets:
                (bundles / name).touch()
        binary = self.directory / "gh"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "args = sys.argv[1:]\n"
            "if args[:2] == ['release', 'view']:\n"
            "    sys.exit(0 if os.environ['RELEASE_EXISTS'] == 'true' else 1)\n"
            "with open(os.environ['GH_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(args) + '\\n')\n"
            "sys.exit(1 if os.environ['RELEASE_FAIL'] == 'true' else 0)\n"
        )
        binary.chmod(0o755)
        log = self.directory / "gh.jsonl"
        result = self.run_step(
            "release", "Create the release and upload the tested bundles",
            PATH=f"{self.directory}:{os.environ['PATH']}", STABLE=stable,
            RELEASE_EXISTS=exists, RELEASE_FAIL=fail, GH_LOG=str(log),
        )
        commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, commands

    def test_stable_release_includes_both_bundles_and_verifies_tag(self):
        result, commands = self.release_commands()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 1)
        args = commands[0]
        self.assertEqual(args[:3], ["release", "create", "v1.2.3"])
        self.assertIn("--verify-tag", args)
        self.assertIn("--generate-notes", args)
        self.assertIn("bundles/example-x86_64.flatpak", args)
        self.assertIn("bundles/example-addon-x86_64.flatpak", args)
        self.assertNotIn("--prerelease", args)

    def test_prerelease_cannot_become_latest(self):
        result, commands = self.release_commands(stable="false")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--prerelease", commands[0])
        self.assertIn("--latest=false", commands[0])

    def test_retry_uploads_to_existing_release(self):
        result, commands = self.release_commands(exists="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[1], ["release", "edit", "v1.2.3", "--draft=false"])
        self.assertEqual(commands[0][:3], ["release", "upload", "v1.2.3"])
        self.assertIn("--clobber", commands[0])

    def test_missing_bundles_prevents_release_creation(self):
        result, commands = self.release_commands(assets=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands, [])

    def test_failed_retry_upload_does_not_publish_draft(self):
        result, commands = self.release_commands(exists="true", fail="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:2], ["release", "upload"])

    def test_creation_failure_fails_the_step(self):
        result, _ = self.release_commands(fail="true")
        self.assertNotEqual(result.returncode, 0)

    def test_existing_prerelease_is_demoted_before_upload(self):
        result, commands = self.release_commands(stable="false", exists="true")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands[0], [
            "release", "edit", "v1.2.3", "--prerelease", "--latest=false",
        ])
        self.assertEqual(len(commands), 3)
        self.assertEqual(commands[2], ["release", "edit", "v1.2.3", "--draft=false"])
        self.assertEqual(commands[1][:3], ["release", "upload", "v1.2.3"])
        self.assertIn("--clobber", commands[1])

    def test_failed_prerelease_edit_prevents_upload(self):
        result, commands = self.release_commands(
            stable="false", exists="true", fail="true",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:2], ["release", "edit"])

    def evaluate(self, expression, **context):
        # Evaluate the workflow's boolean expressions against event/job cases.
        expression = expression.removeprefix("${{").removesuffix("}}")
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = re.sub(r"!(?!=)", " not ", expression)
        cancelled = context.pop("cancelled", False)
        return eval(" ".join(expression.split()), {"__builtins__": {}}, {
            "startsWith": lambda value, prefix: value.startswith(prefix),
            "cancelled": lambda: cancelled,
            **context,
        })

    def test_publication_event_policy(self):
        arches = next(step for step in WORKFLOW["jobs"]["setup"]["steps"]
                      if step.get("id") == "arches")
        for event, ref, stable, enabled, expected in (
            ("push", "refs/tags/v1.2.3", "true", "true", True),
            ("push", "refs/tags/v1.2.3-rc1", "false", "true", False),
            ("push", "refs/tags/v1.2.3", "true", "false", False),
            ("push", "refs/heads/main", "", "true", False),
            ("workflow_dispatch", "refs/heads/main", "", "true", True),
            ("workflow_dispatch", "refs/heads/update/upstream", "", "true", False),
            ("workflow_dispatch", "refs/tags/v1.2.3-rc1", "false", "true", False),
            ("pull_request", "refs/pull/1/merge", "", "true", False),
        ):
            for cache_only in (False, True):
                with self.subTest(event=event, ref=ref, enabled=enabled,
                                  cache_only=cache_only):
                    actual = self.evaluate(
                        arches["env"]["PUBLISH"],
                        github=SimpleNamespace(event_name=event, ref=ref),
                        inputs=SimpleNamespace(cache_only=cache_only),
                        vars=SimpleNamespace(PUBLISH_FLATPAK=enabled),
                        steps=SimpleNamespace(release=SimpleNamespace(
                            outputs=SimpleNamespace(stable=stable))),
                    )
                    self.assertEqual(actual, expected and not cache_only)

    def test_release_waits_for_validation_and_required_deployment(self):
        for publish in ("true", "false"):
            defaults = dict(setup="success", build="success",
                            publish="success" if publish == "true" else "skipped",
                            deploy="success" if publish == "true" else "skipped")
            cases = [(defaults, "refs/tags/v1.2.3", False, True),
                     (defaults, "refs/tags/v1.2.3-rc1", False, True),
                     (defaults, "refs/heads/main", False, False),
                     (defaults, "refs/tags/v1.2.3", True, False)]
            for job in defaults:
                for result in ("failure", "cancelled", "skipped"):
                    if result != defaults[job]:
                        cases.append((dict(defaults, **{job: result}),
                                      "refs/tags/v1.2.3", False, False))
            for results, ref, cancelled, expected in cases:
                for cache_only in (False, True):
                    with self.subTest(publish=publish, results=results, ref=ref,
                                      cache_only=cache_only):
                        needs = SimpleNamespace(**{
                            job: SimpleNamespace(result=result)
                            for job, result in results.items()
                        })
                        needs.setup.outputs = SimpleNamespace(publish=publish)
                        actual = self.evaluate(
                            WORKFLOW["jobs"]["release"]["if"], needs=needs,
                            inputs=SimpleNamespace(cache_only=cache_only),
                            github=SimpleNamespace(ref=ref), cancelled=cancelled,
                        )
                        self.assertEqual(actual, expected and not cache_only)

    def test_triggers_checkout_and_release_permissions(self):
        triggers = WORKFLOW[True]  # PyYAML's YAML 1.1 parses `on` as True.
        self.assertEqual(triggers["push"], {"tags": ["v*"]})
        self.assertIn("pull_request", triggers)
        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("release", triggers)
        for job in ("setup", "build", "publish"):
            checkout = WORKFLOW["jobs"][job]["steps"][0]
            self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
        release = WORKFLOW["jobs"]["release"]
        self.assertEqual(set(release["needs"]), {"setup", "build", "publish", "deploy"})
        self.assertEqual(release["permissions"], {"contents": "write"})
        self.assertEqual(release["env"]["GH_TOKEN"], "${{ github.token }}")
        self.assertEqual(release["env"]["GH_REPO"], "${{ github.repository }}")

    def test_announcement_waits_for_deployment_and_uses_separate_credentials(self):
        job = WORKFLOW["jobs"]["announce"]
        self.assertEqual(job["needs"], "deploy")
        self.assertNotIn("if", job)  # Default success() skips failed/skipped deployment.
        self.assertEqual(job["permissions"], {})
        self.assertEqual(len(job["steps"]), 1)
        step = job["steps"][0]
        self.assertEqual(step["env"]["GH_TOKEN"], "${{ secrets.FLATPAK_REPO_DISPATCH_TOKEN }}")
        self.assertNotIn("uses", step)  # No checkout or build with the dispatch token.

    def test_announcement_dispatches_once_and_reports_missing_or_rejected_credentials(self):
        binary = self.directory / "gh"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['GH_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.exit(int(os.environ.get('GH_EXIT', '0')))\n"
        )
        binary.chmod(0o755)
        log = self.directory / "gh.jsonl"
        env = dict(PATH=f"{self.directory}:{os.environ['PATH']}", GH_LOG=str(log))
        missing = self.run_step("announce", "Announce the publication to the shared remote", GH_TOKEN="", **env)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("::error::Set FLATPAK_REPO_DISPATCH_TOKEN", missing.stdout)
        self.assertFalse(log.exists())
        for status in (0, 1):
            result = self.run_step("announce", "Announce the publication to the shared remote", GH_TOKEN="fixture-token", GH_EXIT=str(status), **env)
            self.assertEqual(result.returncode, status)
            self.assertNotIn("fixture-token", result.stdout + result.stderr)
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(commands, [["api", "--method", "POST", "repos/nosini/flatpak-repo/dispatches", "-f", "event_type=app-published"]] * 2)

    def test_auto_merge_does_not_dispatch_publication(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/update.yml").read_text())
        merge = next(step for step in workflow["jobs"]["check"]["steps"]
                     if step.get("name") == "Merge the update after a successful build")
        self.assertIn("gh pr merge", merge["run"])
        self.assertNotIn("gh workflow run", merge["run"])


if __name__ == "__main__":
    unittest.main()
