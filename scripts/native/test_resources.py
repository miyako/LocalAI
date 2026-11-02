"""Fixture source-to-resource tests, not hosted builds or 4D compilation."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest

import native
import resources


SHA = "a" * 40
BUILDER = "b" * 40


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.output = self.root / "stage"
        self.source = {
            "repository": native.UPSTREAM, "sha": SHA, "ref": "v4.12.1",
            "version": "v4.12.1", "commit_date": "2026-10-23T10:03:52Z",
            "locks": {name: hashlib.sha256(b"lock\n").hexdigest()
                      for name in native.LOCK_PATHS}}
        self.repo = self.root / "repo"
        for name in (resources.MAC_BINARY, *resources.LEGACY):
            path = self.repo / resources.RESOURCE / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"legacy\n")

    def archive(self, target, mutate=None):
        root = self.root / target
        root.mkdir(exist_ok=True)
        content = {
            "LICENSE-LocalAI": b"license\n", "PACKAGE.txt": b"scope\n",
            "licenses/LICENSE-LocalAI": b"license\n",
            "licenses/go/module/LICENSE": b"Go license\n",
            "licenses/npm/package/LICENSE": b"npm license\n",
            "build-info.txt": (
                f"CGO_ENABLED=0\nGOOS={target.split('-')[0]}\n"
                f"GOARCH={target.split('-')[1]}\n").encode(),
            "runtime-dependencies.txt": (
                b"local-ai:\n /usr/lib/libSystem.B.dylib (compatibility version 1)\n"
                if target == "darwin-arm64" else b"Static ELF\n"),
        }
        for name in native.LOCK_PATHS:
            content["source-locks/" + Path(name).name] = b"lock\n"
        content["licenses/manifest.json"] = json.dumps({
            "schema": 1,
            "files": {name.removeprefix("licenses/"): hashlib.sha256(value).hexdigest()
                      for name, value in content.items() if name.startswith("licenses/")}
        }).encode()
        if target == "darwin-arm64":
            content["bin/local-ai"] = struct.pack("<II", 0xfeedfacf, 0x100000c) + b"fixture"
        else:
            header = bytearray(64)
            header[:6] = b"\x7fELF\x02\x01"
            header[18:20] = struct.pack("<H", 62 if target == "linux-amd64" else 183)
            content["bin/local-ai"] = bytes(header)
        for name, value in content.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        info = copy.deepcopy(self.source)
        info.update(format=2, target=target, builder_sha=BUILDER, builder_dirty=False,
                    workflow_run="123", binary_sha256=native.digest(root / "bin/local-ai"),
                    macos_signing="ad-hoc, not notarized" if target == "darwin-arm64" else None,
                    smoke={"passed": True, "checks": resources.SMOKE_CHECKS},
                    files={name: native.digest(root / name) for name in content})
        if mutate:
            mutate(root, info)
        (root / "provenance.json").write_text(json.dumps(info))
        name = f"local-ai-v4.12.1-{SHA[:12]}-{target}-server-cli-only"
        archive = self.artifacts / (name + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for path in sorted(root.rglob("*")):
                tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        (self.artifacts / (name + ".sha256")).write_text(f"{native.digest(archive)}  {archive.name}\n")
        return archive

    def matrix(self, target_mutation=None):
        for target in resources.TARGETS:
            self.archive(target, target_mutation)

    def prepare(self):
        return resources.prepare(self.artifacts, self.source, BUILDER, self.output)

    def test_complete_matrix_installs_only_arm64_and_metadata_and_verifies(self):
        self.matrix()
        self.prepare()
        legacy = {name: (self.repo / resources.RESOURCE / name).read_bytes() for name in resources.LEGACY}
        with contextlib.redirect_stdout(io.StringIO()):
            resources.install(self.output, self.repo)
            resources.verify(self.repo)
        for name, content in legacy.items():
            self.assertEqual((self.repo / resources.RESOURCE / name).read_bytes(), content)
        self.assertEqual((self.repo / resources.RESOURCE / resources.MAC_BINARY).stat().st_mode & 0o777, 0o755)
        self.assertFalse((self.repo / resources.RESOURCE / "native/linux-amd64/bin").exists())

    def test_incomplete_or_duplicate_matrix_never_creates_output(self):
        archive = self.archive("darwin-arm64")
        with self.assertRaisesRegex(ValueError, "every supported target"):
            self.prepare()
        self.matrix()
        duplicate = self.artifacts / "extra"
        duplicate.mkdir()
        (duplicate / archive.name).write_bytes(archive.read_bytes())
        with self.assertRaisesRegex(ValueError, "every supported target"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_archive_checksum_mismatch(self):
        self.matrix()
        archive = next(self.artifacts.glob("*.tar.gz"))
        with archive.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "Archive checksum mismatch"):
            self.prepare()

    def test_mixed_source_or_builder_or_unsmoked_rejected(self):
        for key, value in (("sha", "c" * 40), ("builder_sha", "d" * 40),
                           ("smoke", {"passed": False}), ("builder_dirty", True),
                           ("format", 1)):
            with self.subTest(key=key):
                self.matrix(lambda root, info: info.update({key: value}))
                with self.assertRaisesRegex(ValueError, "provenance"):
                    self.prepare()
                self.assertFalse(self.output.exists())

    def test_content_tampering_is_rejected(self):
        self.matrix(lambda root, info: (root / "LICENSE-LocalAI").write_text("tampered"))
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            self.prepare()

    def test_dependency_license_inventory_is_independently_verified(self):
        def mutate(root, info):
            license_file = root / "licenses/go/module/LICENSE"
            license_file.write_text("changed legal text")
            info["files"]["licenses/go/module/LICENSE"] = native.digest(license_file)
        self.matrix(mutate)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_mixed_workflow_runs_are_rejected(self):
        self.matrix(lambda root, info: info.update(
            workflow_run="456" if info["target"] == "darwin-arm64" else "123"))
        with self.assertRaisesRegex(ValueError, "Mixed native workflow runs"):
            self.prepare()

    def test_wrong_architecture_even_with_updated_hash_is_rejected(self):
        def mutate(root, info):
            if info["target"] == "darwin-arm64":
                (root / "bin/local-ai").write_bytes(b"wrong" * 20)
                checksum = native.digest(root / "bin/local-ai")
                info["binary_sha256"] = info["files"]["bin/local-ai"] = checksum
        self.matrix(mutate)
        with self.assertRaisesRegex(ValueError, "arm64 Mach-O"):
            self.prepare()

    def test_transient_resources_do_not_use_git_blob_size_limit(self):
        size = 100 * 1024 * 1024 + 1
        def grow(root, info):
            if info["target"] == "darwin-arm64":
                binary = root / "bin/local-ai"
                with binary.open("r+b") as stream:
                    stream.truncate(size)
                checksum = native.digest(binary)
                info["binary_sha256"] = info["files"]["bin/local-ai"] = checksum
        self.matrix(grow)
        self.prepare()
        self.assertTrue(self.output.is_dir())
        self.assertEqual((self.output / resources.RESOURCE / resources.MAC_BINARY).stat().st_size, size)
        self.assertEqual((self.repo / resources.RESOURCE / resources.MAC_BINARY).read_bytes(), b"legacy\n")

    def test_read_only_validation_does_not_write_resources(self):
        self.matrix()
        result = resources.prepare(self.artifacts, self.source, BUILDER)
        self.assertEqual(set(result), resources.TARGETS)
        self.assertFalse(self.output.exists())

    def test_packaged_resource_tamper_fails_publish_guard(self):
        self.matrix()
        self.prepare()
        with contextlib.redirect_stdout(io.StringIO()):
            resources.install(self.output, self.repo)
        (self.repo / resources.RESOURCE / resources.LEGACY[0]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            resources.verify(self.repo)

    def test_packaged_resource_directory_contract(self):
        self.matrix()
        self.prepare()
        with contextlib.redirect_stdout(io.StringIO()):
            resources.install(self.output, self.repo)
            resources.verify(Path("."), resource_dir=self.repo / resources.RESOURCE)

    def test_allow_legacy_never_masks_incomplete_native_update(self):
        with contextlib.redirect_stdout(io.StringIO()):
            resources.verify(self.repo, allow_legacy=True)
        (self.repo / resources.RESOURCE / "native").mkdir()
        with self.assertRaisesRegex(ValueError, "provenance is missing"):
            resources.verify(self.repo, allow_legacy=True)

    def test_archive_paths_and_links_fail_closed(self):
        for name in ("../escape", "/absolute", "a\\b", "a//b", "C:/file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                resources.portable(name)
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "/outside"
            tar.addfile(member)
        with self.assertRaisesRegex(ValueError, "links/special"):
            resources.unpack(archive, self.root / "unpacked")

    def test_lf_source_lock_survives_windows_style_git_checkout(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        for name in (".gitattributes", "scripts/native/source-lock.json"):
            destination = checkout / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((Path(__file__).resolve().parents[2] / name).read_bytes())
        (checkout / "control.txt").write_bytes(b"control\n")
        subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
        expected = (checkout / "scripts/native/source-lock.json").read_bytes()
        for name in ("scripts/native/source-lock.json", "control.txt"):
            (checkout / name).unlink()
        subprocess.run(["git", "-C", str(checkout), "-c", "core.autocrlf=true",
                        "-c", "core.eol=crlf", "checkout-index", "-a", "-f"], check=True)
        self.assertEqual((checkout / "scripts/native/source-lock.json").read_bytes(), expected)
        self.assertEqual((checkout / "control.txt").read_bytes(), b"control\r\n")


if __name__ == "__main__":
    unittest.main()
