"""Mocked release transport with real archive-to-resource fixture validation."""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import unittest

import release
import resources
import test_resources


TAG = "server-v4.12.1-aaaaaaaaaaaa-123-1"
BUILDER = test_resources.BUILDER


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_resources.ResourceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.matrix()
        self.source = self.fixture.source
        self.root = self.fixture.root
        self.lock_path = self.root / "component-lock.json"
        sums = self.fixture.artifacts / "SHA256SUMS"
        sums.write_text("".join(
            (archive.with_name(archive.name.removesuffix(".tar.gz") + ".sha256")).read_text()
            for archive in sorted(self.fixture.artifacts.glob("*.tar.gz"))))
        self.paths = sorted(self.fixture.artifacts.glob("*.tar.gz")) + [sums]
        self.assets = [{"name": path.name, "id": index + 10, "size": path.stat().st_size,
                        "state": "uploaded"} for index, path in enumerate(self.paths)]
        self.release = {"tag_name": TAG, "draft": False, "prerelease": False,
                        "id": 1234, "assets": self.assets}
        self.lookup_calls = []
        self.download_calls = []

    def lookup(self, endpoint):
        self.lookup_calls.append(endpoint)
        if endpoint.startswith("commits/"):
            return {"sha": BUILDER}
        return copy.deepcopy(self.release)

    def download(self, asset, path):
        self.download_calls.append(asset["id"])
        original = next(item for item in self.assets if item["id"] == asset["id"])
        shutil.copyfile(self.fixture.artifacts / original["name"], path)

    def adopt(self):
        return release.adopt(TAG, self.source, self.lock_path, self.lookup, self.download)

    def test_adopt_then_locked_prepare_then_transient_install_and_package_verify(self):
        lock = self.adopt()
        self.assertEqual(lock["release"]["builder_sha"], BUILDER)
        self.assertEqual(set(lock["assets"]), release.asset_names(self.source))
        self.assertFalse((self.fixture.repo / resources.RESOURCE / "native").exists())
        output = self.root / "release-stage"
        with contextlib.redirect_stdout(io.StringIO()):
            release.prepare(self.lock_path, output, self.lookup, self.download)
            resources.install(output, self.fixture.repo)
            resources.verify(Path("."), resource_dir=self.fixture.repo / resources.RESOURCE)
        for asset in lock["assets"].values():
            self.assertRegex(asset["sha256"], r"^[a-f0-9]{64}$")

    def test_unconfigured_lock_fails_before_network_or_versioning(self):
        self.lock_path.write_text('{"format":1,"status":"unconfigured"}')
        with self.assertRaisesRegex(ValueError, "No latest/legacy fallback"):
            release.prepare(self.lock_path, self.root / "output", self.lookup, self.download)
        self.assertEqual(self.lookup_calls, [])
        self.assertEqual(self.download_calls, [])

    def test_missing_native_release_does_not_write_lock(self):
        def missing(endpoint):
            raise RuntimeError("HTTP 404 native release missing")
        with self.assertRaisesRegex(RuntimeError, "404"):
            release.adopt(TAG, self.source, self.lock_path, missing, self.download)
        self.assertFalse(self.lock_path.exists())

    def test_no_latest_component_draft_prerelease_or_partial_release(self):
        for tag in ("latest", "20.1.2", "../server-x"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.release_info(tag, self.source, self.lookup)
        for key in ("draft", "prerelease"):
            self.release[key] = True
            with self.assertRaises(ValueError):
                self.adopt()
            self.release[key] = False
        self.release["assets"] = self.assets[:-1]
        with self.assertRaisesRegex(ValueError, "complete three-target"):
            self.adopt()
        self.assertFalse(self.lock_path.exists())

    def test_changed_release_asset_identity_is_rejected(self):
        self.adopt()
        self.assets[0]["id"] += 500
        with self.assertRaisesRegex(ValueError, "identity changed"):
            release.prepare(self.lock_path, self.root / "output", self.lookup, self.download)
        self.assertFalse((self.root / "output").exists())

    def test_changed_release_tag_is_rejected(self):
        self.adopt()
        def moved(endpoint):
            result = self.lookup(endpoint)
            return {"sha": "c" * 40} if endpoint.startswith("commits/") else result
        with self.assertRaisesRegex(ValueError, "identity changed"):
            release.prepare(self.lock_path, self.root / "output", moved, self.download)

    def test_changed_same_size_asset_bytes_fail_locked_checksum(self):
        self.adopt()
        path = self.paths[0]
        data = bytearray(path.read_bytes())
        data[20] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "Locked release asset checksum"):
            release.prepare(self.lock_path, self.root / "output", self.lookup, self.download)
        self.assertFalse((self.root / "output").exists())

    def test_changed_release_during_download_is_rejected(self):
        def downloader(asset, path):
            self.download(asset, path)
            if len(self.download_calls) == 4:
                self.release["id"] += 1
        with self.assertRaisesRegex(ValueError, "changed while downloading"):
            release.adopt(TAG, self.source, self.lock_path, self.lookup, downloader)
        self.assertFalse(self.lock_path.exists())

    def test_checksums_require_exact_closure(self):
        path = self.root / "sums"
        for text in ("", "bad\n", "a" * 64 + "  ../escape.tar.gz\n",
                     ("a" * 64 + "  archive.tar.gz\n") * 2):
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                release.checksums(path, {"archive.tar.gz"})

    def test_repository_lock_is_valid_or_explicitly_unconfigured(self):
        data = json.loads(release.LOCK.read_text())
        if data.get("status") == "unconfigured":
            with self.assertRaisesRegex(ValueError, "unconfigured"):
                release.load_lock()
        else:
            release.load_lock()


class WorkflowContractTests(unittest.TestCase):
    def test_publish_fetches_before_version_but_overlays_after_clean_versioning(self):
        text = (Path(__file__).resolve().parents[2] / ".github/workflows/publish.yml").read_text()
        for job in text.split("      - name: configure")[1:]:
            self.assertLess(job.index("release.py prepare"), job.index("package-set-version"))
            self.assertLess(job.index("package-set-version"), job.index("resources.py install"))
            self.assertLess(job.index("resources.py install"), job.index("actions/build-component"))
            self.assertIn("resources.py verify --resources", job)
            self.assertNotIn("build.sh", job)
            self.assertNotIn("git add", job)
        native_workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/build-server.yml").read_text()
        self.assertNotIn("update-resources:", native_workflow)
        self.assertNotIn("git push", native_workflow)
        self.assertIn("--latest=false", native_workflow)


if __name__ == "__main__":
    unittest.main()
