import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("native", Path(__file__).with_name("native.py"))
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

SHA = "ec9274027eadd552d56f2c6c1fe86cd9216a991a"


class ResolveTests(unittest.TestCase):
    def lookup(self, endpoint):
        self.calls.append(endpoint)
        if endpoint == "releases/latest":
            return {"tag_name": "v4.12.1", "draft": False, "prerelease": False}
        return {"sha": SHA, "commit": {"committer": {"date": "2026-10-23T09:00:00Z"}}}

    def setUp(self):
        self.calls = []

    def test_latest_resolved_once(self):
        result = native.resolve("", self.lookup)
        self.assertEqual(self.calls, ["releases/latest", "commits/v4.12.1"])
        self.assertEqual(result["sha"], SHA)
        self.assertEqual(result["version"], "v4.12.1")

    def test_tag_override_does_not_query_latest(self):
        self.assertEqual(native.resolve("v4.12.1", self.lookup)["ref"], "v4.12.1")
        self.assertEqual(self.calls, ["commits/v4.12.1"])

    def test_sha_override(self):
        self.assertEqual(native.resolve(SHA, self.lookup)["version"], "sha-" + SHA[:12])
        self.assertEqual(self.calls, ["commits/" + SHA])

    def test_reject_mutable_or_unsafe_refs(self):
        for ref in ("main", "master", "--help", "v4.12.1\nx=1", "$(id)", "ec927402"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                native.resolve(ref, self.lookup)
        self.assertEqual(self.calls, [])

    def test_reject_prerelease_as_default(self):
        with self.assertRaises(ValueError):
            native.resolve("", lambda _: {"draft": False, "prerelease": True})

    def test_reject_wrong_sha(self):
        with self.assertRaises(ValueError):
            native.resolve("a" * 40, self.lookup)

    def test_supported_hosts_match_upstream_server_scope(self):
        self.assertEqual(set(native.TARGETS.values()),
                         {"darwin-arm64", "linux-amd64", "linux-arm64"})


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.source.mkdir()
        for name in ("local-ai", "LICENSE", "go.mod", "go.sum",
                     "core/http/react-ui/package-lock.json"):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n")
        self.metadata = root / "source.json"
        self.metadata.write_text(json.dumps({
            "sha": SHA, "version": "v4.12.1", "repository": native.UPSTREAM,
            "ref": "v4.12.1", "commit_date": "2026-10-23T09:00:00Z",
        }))
        self.output = root / "output"
        self.dynamic = False
        self.arch = "amd64"
        self.go_os = "linux"
        self.system = "Linux"
        self.machine = "x86_64"
        self.third_party_library = False

    def command(self, *args, **kwargs):
        if args[:2] == ("git", "rev-parse"):
            return SHA
        if args[:3] == ("go", "version", "-m"):
            return f"CGO_ENABLED=0\nGOOS={self.go_os}\nGOARCH={self.arch}"
        if args[0] == "readelf":
            return "(NEEDED) libmissing.so" if self.dynamic else "Static ELF\n"
        if args[0] == "otool":
            library = "/opt/homebrew/lib/libmissing.dylib" if self.third_party_library else "/usr/lib/libSystem.B.dylib"
            return f"local-ai:\n\t{library} (compatibility version 1.0.0)\n"
        return "fixture tool version"

    def package(self):
        with patch.object(native.platform, "system", return_value=self.system), \
                patch.object(native.platform, "machine", return_value=self.machine), \
                patch.object(native, "command", side_effect=self.command), \
                contextlib.redirect_stdout(io.StringIO()):
            native.package(self.source, self.metadata, self.output)

    def test_archive_shape_checksums_and_provenance(self):
        self.package()
        archive, = self.output.glob("*.tar.gz")
        checksum, = self.output.glob("*.sha256")
        self.assertIn("ec9274027ead-linux-amd64-server-cli-only", archive.name)
        self.assertEqual(checksum.read_text(), f"{native.digest(archive)}  {archive.name}\n")
        with tarfile.open(archive) as tar:
            self.assertEqual(tar.getmember("bin/local-ai").mode, 0o755)
            info = json.load(tar.extractfile("provenance.json"))
            self.assertEqual(info["sha"], SHA)
            self.assertEqual(info["target"], "linux-amd64")
            self.assertEqual(info["binary_sha256"], native.digest(self.source / "local-ai"))
            self.assertIn("source-locks/package-lock.json", tar.getnames())
            self.assertIn("LICENSE-LocalAI", tar.getnames())
        first_hash = native.digest(archive)
        self.package()
        self.assertEqual(native.digest(archive), first_hash)

    def test_unbundled_linux_dynamic_library_is_fatal(self):
        self.dynamic = True
        with self.assertRaisesRegex(ValueError, "static CGO-disabled"):
            self.package()
        self.assertFalse(self.output.exists())

    def test_wrong_checkout_is_fatal(self):
        info = json.loads(self.metadata.read_text())
        info["sha"] = "a" * 40
        self.metadata.write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError, "Checkout does not match"):
            self.package()

    def test_cross_compiled_binary_is_rejected(self):
        self.arch = "arm64"
        with self.assertRaisesRegex(ValueError, "GOARCH=amd64"):
            self.package()

    def test_macos_system_libraries_are_allowed(self):
        self.system, self.machine, self.go_os, self.arch = "Darwin", "arm64", "darwin", "arm64"
        self.package()
        archive, = self.output.glob("*darwin-arm64-server-cli-only.tar.gz")
        with tarfile.open(archive) as tar:
            info = json.load(tar.extractfile("provenance.json"))
            self.assertEqual(info["macos_signing"], "ad-hoc, not notarized")

    def test_unbundled_macos_library_is_fatal(self):
        self.system, self.machine, self.go_os, self.arch = "Darwin", "arm64", "darwin", "arm64"
        self.third_party_library = True
        with self.assertRaisesRegex(ValueError, "Unbundled non-system macOS"):
            self.package()

    def test_intel_macos_is_not_a_new_server_target(self):
        self.system = "Darwin"
        with self.assertRaisesRegex(ValueError, "Unsupported native host"):
            self.package()


if __name__ == "__main__":
    unittest.main()
