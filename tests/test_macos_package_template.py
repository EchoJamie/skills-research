"""Exercise packaging ownership, failure propagation and cleanup with tool doubles."""

import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "skills/apple-app-development/assets/build-dmg.sh"
)

# Tool doubles model command failures and output ownership; real signing/DMG
# compatibility is checked separately on macOS, not claimed by these tests.
TOOL = r'''
import os
from pathlib import Path
import plistlib
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
state = Path(os.environ["TEST_STATE"])
failure = os.environ.get("FAIL_STAGE", "")
with (state / "calls").open("a") as log:
    log.write(name + " " + " ".join(args) + "\n")

if name == "swift":
    (Path(os.environ["TMPDIR"]) / "compiler-temporary").write_text("temporary")
    if failure == "build":
        sys.exit(23)
    binary_dir = Path.cwd() / ".build/release"
    binary_dir.mkdir(parents=True, exist_ok=True)
    if "--show-bin-path" in args:
        print(binary_dir)
    else:
        (binary_dir / "ExampleApp").write_text(os.environ.get("BUILD_CONTENT", "first"))
elif name == "plutil":
    with open(args[-1], "rb") as handle:
        info = plistlib.load(handle)
    if args[0] == "-extract":
        print(info[args[1]])
elif name == "lipo":
    print("arm64")
elif name == "codesign":
    if failure == "sign" and "--sign" in args:
        sys.exit(24)
elif name == "lsof":
    sys.exit(0 if failure == "occupied" else 1)
elif name == "hdiutil":
    if args[0] == "create":
        output = Path(args[-1])
        output.write_text("image:" + os.environ.get("BUILD_CONTENT", "first"))
        if failure == "create":
            sys.exit(26)
'''


@unittest.skipUnless(Path("/bin/bash").exists(), "requires Bash")
class MacosPackageTemplateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="package-template-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        for directory in ("scripts", "Resources", "dist", "tmp", "tools", "state"):
            (self.root / directory).mkdir(parents=True)
        shutil.copyfile(TEMPLATE, self.root / "scripts/build-dmg.sh")
        with (self.root / "Resources/Info.plist").open("wb") as handle:
            plistlib.dump({
                "CFBundleShortVersionString": "1.2.3",
                "CFBundleExecutable": "ExampleApp",
                "CFBundleIdentifier": "example.template.fixture",
            }, handle)
        for name in ("swift", "plutil", "lipo", "codesign", "hdiutil", "lsof"):
            tool = self.root / "tools" / name
            tool.write_text(f"#!{sys.executable}\n" + TOOL)
            tool.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.root / "tools") + os.pathsep + os.environ["PATH"],
            "TMPDIR": str(self.root / "tmp"),
            "TEST_STATE": str(self.root / "state"),
            "SIGNING_IDENTITY": "Apple Development: Fixture",
        }
        self.dmg = self.root / "dist/ExampleApp-1.2.3-arm64.dmg"
        self.sentinel = self.root / "dist/user-owned.txt"
        self.sentinel.write_text("keep")

    def run_package(self, **overrides):
        return subprocess.run(
            ["/bin/bash", str(self.root / "scripts/build-dmg.sh")],
            env={**self.env, **overrides}, text=True, capture_output=True,
        )

    def assert_clean(self):
        self.assertEqual(list((self.root / "tmp").iterdir()), [])
        self.assertEqual(self.sentinel.read_text(), "keep")

    def test_release_and_same_version_rebuild_replace_only_expected_output(self):
        first = self.run_package()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.dmg.read_text(), "image:first")
        self.assert_clean()
        second = self.run_package(BUILD_CONTENT="second")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.dmg.read_text(), "image:second")
        self.assertEqual(set(p.name for p in self.dmg.parent.iterdir()), {
            self.dmg.name, "user-owned.txt",
        })
        self.assertEqual((self.root / ".build/release/ExampleApp").read_text(), "second")
        calls = (self.root / "state/calls").read_text()
        self.assertIn("swift build -c release --product ExampleApp", calls)
        self.assert_clean()

    def test_build_or_sign_failure_leaves_no_new_delivery_or_staging(self):
        for stage in ("build", "sign"):
            with self.subTest(stage=stage):
                result = self.run_package(FAIL_STAGE=stage)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.dmg.exists())
                self.assert_clean()

    def test_failed_rebuild_removes_partial_image_without_restoring_old_one(self):
        self.dmg.write_text("obsolete")
        result = self.run_package(FAIL_STAGE="create")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.dmg.exists())
        self.assert_clean()

    def test_occupied_image_is_not_removed(self):
        self.dmg.write_text("in use")
        result = self.run_package(FAIL_STAGE="occupied")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.dmg.read_text(), "in use")
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
