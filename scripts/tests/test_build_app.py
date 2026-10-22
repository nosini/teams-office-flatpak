"""Check the Flatpak build's source, cache and output paths in both layouts."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class BuildAppTests(unittest.TestCase):
    def build(self, reorganized):
        scratch = ROOT / ".cache" / "test-build-app"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            work = Path(directory)
            source = work / "source"
            source.mkdir()
            app = source / "fixture-app" if reorganized else source
            builder = app / "node_modules/.bin/electron-builder"
            builder.parent.mkdir(parents=True)
            builder.write_text(
                "#!/usr/bin/env bash\nset -eu\n"
                "printf '%s\\n' \"$PWD\" \"$@\" > \"$BUILD_LOG\"\n"
                "mkdir -p dist/linux-unpacked/resources\n"
                "printf app > dist/linux-unpacked/resources/app.asar\n"
            )
            builder.chmod(0o755)
            icon = app / "app/assets/icons/icon-256x256.png"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"fixture icon")
            (source / "flatpak-node").mkdir()
            (source / "flatpak-node/electron-builder-arch-args.sh").write_text(
                "ELECTRON_BUILDER_ARCH_ARGS=--arm64\n"
            )
            if reorganized:
                (source / "scripts").mkdir()
                (source / "scripts/prepare-app.js").write_text(
                    'require("node:fs").cpSync("fixture-app", "build/teams-office", {recursive:true});\n'
                )
            binaries = work / "bin"
            binaries.mkdir()
            for name, contents in {
                "npm": 'printf "%s\\n" "$PWD" "$@" > "$INSTALL_LOG"\n',
                "patch-electron-desktop-filename": 'test -f "$1"\n',
            }.items():
                executable = binaries / name
                executable.write_text("#!/usr/bin/env bash\nset -eu\n" + contents)
                executable.chmod(0o755)
            user_home = work / "home"
            user_home.mkdir()
            cache = source / "flatpak-node/cache"
            (cache / "node-gyp").mkdir(parents=True)
            destination = work / "install"
            destination.mkdir()
            build_log, install_log = work / "build.log", work / "install.log"
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/build-app.sh")], cwd=source,
                env=dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}",
                         HOME=str(user_home), XDG_CACHE_HOME=str(cache),
                         FLATPAK_DEST=str(destination), FLATPAK_ID="eu.example.App",
                         BUILD_LOG=str(build_log), INSTALL_LOG=str(install_log)),
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = source / "build/teams-office" if reorganized else source
            self.assertEqual(install_log.read_text().splitlines(),
                             [str(expected), "ci", "--ignore-scripts"])
            args = build_log.read_text().splitlines()
            self.assertEqual(args[0], str(expected))
            self.assertIn("--arm64", args)
            self.assertIn("-c.electronDist=" + str(cache / "electron"), args)
            self.assertEqual((destination / "teams-office/resources/app.asar").read_text(), "app")
            self.assertEqual((destination / "share/icons/hicolor/256x256/apps/eu.example.App.png").read_bytes(), b"fixture icon")

    def test_original_source_tags(self):
        self.build(reorganized=False)

    def test_submodule_source_layout(self):
        self.build(reorganized=True)


if __name__ == "__main__":
    unittest.main()
