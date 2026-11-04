import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("licenses", Path(__file__).with_name("licenses.py"))
licenses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(licenses)


MIT_TEXT = b"""MIT License

Copyright (c) upstream author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED.
"""


APACHE_HEADER = b"""Copyright 2020 Example Authors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
"""
PUBLIC_DOMAIN_TEXT = (b"All the files in this package have been written by the authors.\n"
                      b"All these files have been put into the public domain.\n")


class LicenseTests(unittest.TestCase):
    def setUp(self):
        # All scratch data stays inside this worktree, including on macOS.
        self.temp = tempfile.TemporaryDirectory(prefix=".license-test-", dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.ui = self.source / licenses.UI
        self.ui.mkdir(parents=True)
        self.output = self.root / "licenses"
        self.calls = []
        self.original = b"immutable upstream license\r\ncopyright\xff\n"
        (self.source / "LICENSE").write_bytes(b"working tree CRLF conversion\r\n")
        self.root_metadata = {
            "name": "ui", "version": "1.0.0",
            "dependencies": {"alpha": "1.0.0"},
            "optionalDependencies": {"absent": "1.0.0", "optional": "1.0.0"},
            "devDependencies": {"dev": "1.0.0"},
        }
        self.packages = {"": copy.deepcopy(self.root_metadata)}
        self.add_package("node_modules/alpha", dependencies={"@scope/beta": "2.0.0"})
        self.add_package("node_modules/@scope/beta", name="@scope/beta", version="2.0.0",
                         license="(MIT OR Apache-2.0)")
        self.add_package("node_modules/optional", optional=True)
        self.add_package("node_modules/absent", optional=True, installed=False)
        self.add_package("node_modules/dev", dev=True, installed=False)
        self.save_lock()
        self.vendored = self.root / "vendored"
        self.vendored_text = MIT_TEXT
        self.vendored_entry = {
            "name": "@scope/native-x64", "version": "1.0.0", "license": "MIT",
            "repository": "https://github.com/example/native", "provenance": "release",
            "release_commit": "c" * 40, "license_commit": "c" * 40,
            "source_path": "LICENSE", "file": f"github.com/example/native/{'c' * 40}/LICENSE",
            "sha256": licenses.sha256(self.vendored_text),
        }
        self.go_text = APACHE_HEADER
        self.go_entry = {
            "module": "example.com/unknown", "version": "v1.2.3",
            "packages": ["example.com/unknown", "example.com/unknown/sub"],
            "license": "Apache-2.0", "provenance": "module", "source_path": "LICENSE",
            "file": "go/example.com/unknown@v1.2.3/LICENSE",
            "sha256": licenses.sha256(self.go_text),
        }
        self.go_module_dir = self.root / "gomod/example.com/unknown@v1.2.3"
        self.go_module_dir.mkdir(parents=True)
        (self.go_module_dir / "LICENSE").write_bytes(self.go_text)
        self.go_build = {
            "example.com/library": ("example.com/library", "v1.0.0", "/mod/library", ""),
            "example.com/unknown": ("example.com/unknown", "v1.2.3",
                                    str(self.go_module_dir), ""),
            "example.com/unknown/sub": ("example.com/unknown", "v1.2.3",
                                        str(self.go_module_dir), ""),
        }
        # Packages go-licenses cannot classify unless --ignore covers them.
        self.go_unknown = ["example.com/unknown", "example.com/unknown/sub"]
        self.go_saves_vendored = False
        self.save_vendored()
        patcher = patch.object(licenses, "VENDORED", self.vendored)
        patcher.start()
        self.addCleanup(patcher.stop)

    def save_vendored(self, entries=None, go_entries=None):
        path = self.vendored / self.vendored_entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.vendored_text)
        path = self.vendored / self.go_entry["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.go_text)
        (self.vendored / "manifest.json").write_text(json.dumps({
            "schema": 1,
            "packages": [self.vendored_entry] if entries is None else entries,
            "go_modules": [self.go_entry] if go_entries is None else go_entries,
        }))

    def add_unlicensed_native(self, name="@scope/native-x64", version="1.0.0",
                              license="MIT"):
        self.root_metadata["optionalDependencies"][name] = version
        self.packages[""] = copy.deepcopy(self.root_metadata)
        self.add_package(f"node_modules/{name}", name=name, version=version,
                         license=license, optional=True)
        for legal in ("LICENSE", "NOTICE"):
            (self.ui / "node_modules" / name / legal).unlink()
        (self.ui / "node_modules" / name / "README.md").write_text("MIT\n")
        self.save_lock()

    def add_package(self, key, *, name=None, version="1.0.0", license="MIT",
                    optional=False, dev=False, installed=True, **extra):
        name = name or key.rsplit("node_modules/", 1)[1]
        metadata = {"name": name, "version": version, "license": license, **extra}
        self.packages[key] = copy.deepcopy(metadata)
        if optional:
            self.packages[key]["optional"] = True
        if dev:
            self.packages[key]["dev"] = True
        if installed:
            path = self.ui / key
            path.mkdir(parents=True)
            (path / "package.json").write_text(json.dumps(metadata))
            (path / "LICENSE").write_bytes(b"Exact package license\r\n")
            (path / "NOTICE").write_bytes(b"Exact copyright notice\n")
        return metadata

    def save_lock(self):
        (self.ui / "package.json").write_text(json.dumps(self.root_metadata))
        (self.ui / "package-lock.json").write_text(json.dumps({
            "name": "ui", "lockfileVersion": 3, "packages": self.packages,
        }))

    def mock_run(self, args, cwd, env=None):
        self.calls.append((args, cwd, env))
        if args == ["git", "rev-parse", "HEAD"]:
            return b"a" * 40 + b"\n"
        if args == ["git", "show", "HEAD:LICENSE"]:
            return self.original
        if args[:4] == ["go", "mod", "download", "-json"]:
            return json.dumps({
                "Path": licenses.GO_MODULE, "Version": licenses.GO_VERSION,
                "Origin": {"Hash": licenses.GO_COMMIT},
                "Sum": "h1:" + "A" * 43 + "=",
                "GoModSum": "h1:" + "B" * 43 + "=",
            }).encode()
        if args[:3] == ["go", "list", "-deps"]:
            self.assertEqual(args[-1], "./cmd/local-ai")
            lines = ["fmt"] + ["\t".join((package, *module))
                               for package, module in self.go_build.items()]
            return ("\n".join(lines) + "\n").encode()
        if args[:2] == ["go", "run"]:
            self.assertEqual(args[2:5], [
                f"{licenses.GO_MODULE}@v2.0.1", "save", "./cmd/local-ai"])
            self.assertEqual(args[-2], "--save_path")
            self.assertEqual(env["CGO_ENABLED"], "0")
            self.assertTrue(env["GOFLAGS"].endswith("-mod=readonly"))
            flags = args[5:-2]
            self.assertEqual(flags[::2], ["--ignore"] * (len(flags) // 2))
            ignored = flags[1::2]
            unknown = [p for p in self.go_unknown
                       if not any(p.startswith(i) for i in ignored)]
            if unknown:
                raise subprocess.CalledProcessError(1, args, b"unknown: " + str(unknown).encode())
            dest = Path(args[-1])
            if self.go_saves_vendored:
                (dest / "example.com/unknown").mkdir(parents=True)
                (dest / "example.com/unknown/LICENSE").write_bytes(b"saved\n")
            (dest / "example.com/library").mkdir(parents=True)
            (dest / "example.com/library/LICENSE").write_bytes(b"Go legal text\n")
            (dest / "example.com/library/NOTICE").write_bytes(b"Go notice\n")
            return b""
        self.fail(f"Unexpected command: {args}")

    def collect(self, output=None):
        with patch.object(licenses, "run", side_effect=self.mock_run), \
                patch.dict(os.environ, {"CGO_ENABLED": "0"}):
            return licenses.collect(self.source, output or self.output)

    def test_complete_closure_immutable_bytes_and_portable_inventory(self):
        before = {p.relative_to(self.source): p.read_bytes()
                  for p in self.source.rglob("*") if p.is_file()}
        result = self.collect()
        self.assertEqual((self.output / "LICENSE-LocalAI").read_bytes(), self.original)
        self.assertEqual({p.relative_to(self.source): p.read_bytes()
                          for p in self.source.rglob("*") if p.is_file()}, before)
        self.assertEqual(result["go"]["commit"], licenses.GO_COMMIT)
        self.assertEqual(result["npm"]["absent_optional"], ["node_modules/absent"])
        self.assertEqual([p["name"] for p in result["npm"]["packages"]],
                         ["@scope/beta", "alpha", "optional"])
        for key, digest in result["files"].items():
            self.assertNotIn("\\", key)
            self.assertEqual(licenses.sha256((self.output / key).read_bytes()), digest)
        self.assertIn("go/example.com/library/NOTICE", result["files"])
        self.assertIn("npm/node_modules/alpha/NOTICE", result["files"])
        self.assertEqual(licenses.verify(self.output), result)

    def test_deterministic_output(self):
        first = self.collect()
        other = self.root / "other"
        self.assertEqual(first, self.collect(other))
        self.assertEqual((self.output / "manifest.json").read_bytes(),
                         (other / "manifest.json").read_bytes())

    def test_missing_license_text(self):
        (self.ui / "node_modules/alpha/LICENSE").unlink()
        with self.assertRaisesRegex(ValueError, "No license text"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_missing_required_transitive(self):
        import shutil
        shutil.rmtree(self.ui / "node_modules/@scope/beta")
        with self.assertRaisesRegex(ValueError, "Missing production"):
            self.collect()

    def test_installed_optional_requires_its_closure(self):
        self.packages["node_modules/optional"]["dependencies"] = {"missing": "1"}
        path = self.ui / "node_modules/optional/package.json"
        data = json.loads(path.read_text())
        data["dependencies"] = {"missing": "1"}
        path.write_text(json.dumps(data))
        self.save_lock()
        with self.assertRaisesRegex(ValueError, "Unresolved production"):
            self.collect()

    def test_unknown_missing_or_malformed_declaration(self):
        path = self.ui / "node_modules/alpha/package.json"
        original = json.loads(path.read_text())
        for value in (None, "", "UNKNOWN", "UNLICENSED", "LicenseRef-unknown",
                      "MIT OR", "MIT AND ()", "SEE LICENSE IN LICENSE", {"type": "MIT"}):
            with self.subTest(value=value):
                path.write_text(json.dumps({**original, "license": value}))
                with self.assertRaises(ValueError):
                    self.collect(self.root / f"bad-{len(self.calls)}")

    def add_font_package(self, license="OFL-1.1"):
        name = "@fontsource-variable/geist"
        self.root_metadata["dependencies"][name] = "5.2.8"
        self.packages[""] = copy.deepcopy(self.root_metadata)
        self.add_package(f"node_modules/{name}", name=name, version="5.2.8", license=license)
        font_license = self.ui / "node_modules" / name / "LICENSE"
        font_license.write_bytes(b"This Font Software is licensed under the "
                                 b"SIL Open Font License, Version 1.1.\n")
        (self.ui / "node_modules" / name / "NOTICE").unlink()
        self.save_lock()
        return name, font_license

    def test_ofl_font_package_collected_with_exact_license_text(self):
        # Upstream web UI fonts (@fontsource-variable/geist[-mono]) declare OFL-1.1.
        name, font_license = self.add_font_package()
        result = self.collect()
        record = next(p for p in result["npm"]["packages"] if p["name"] == name)
        self.assertEqual(record["license"], "OFL-1.1")
        self.assertEqual(record["files"], [f"npm/node_modules/{name}/LICENSE"])
        self.assertEqual((self.output / record["files"][0]).read_bytes(),
                         font_license.read_bytes())
        self.assertEqual(licenses.verify(self.output), result)

    def test_ofl_requires_license_text(self):
        _, font_license = self.add_font_package()
        font_license.unlink()
        with self.assertRaisesRegex(ValueError, "No license text"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_ofl_expressions_and_unreviewed_variants(self):
        for value in ("OFL-1.1", "(OFL-1.1 OR MIT)", "MIT AND OFL-1.1"):
            with self.subTest(value=value):
                self.assertEqual(licenses.spdx(value), value)
        for value in ("OFL-1.0", "OFL-1.1-RFN", "OFL-1.1-no-RFN", "OFL-1.1+",
                      "ofl-1.1", "OFL", "OFL-1.1 OR"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    licenses.spdx(value)

    def test_unreviewed_ofl_variant_fails_collection(self):
        self.add_font_package("OFL-1.1-RFN")
        with self.assertRaisesRegex(ValueError, "Unknown/unsupported SPDX license: OFL-1.1-RFN"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_vendored_license_used_for_exact_name_and_version(self):
        self.add_unlicensed_native()
        result = self.collect()
        record = next(p for p in result["npm"]["packages"]
                      if p["name"] == "@scope/native-x64")
        target = "npm/node_modules/@scope/native-x64/LICENSE.vendored"
        notice = "npm/node_modules/@scope/native-x64/VENDORED-LICENSE-NOTICE.txt"
        self.assertEqual(record["files"], [target, notice])
        self.assertEqual((self.output / target).read_bytes(), self.vendored_text)
        self.assertEqual(record["vendored"], {
            "repository": "https://github.com/example/native", "provenance": "release",
            "release_commit": "c" * 40, "license_commit": "c" * 40,
            "source_path": "LICENSE", "sha256": licenses.sha256(self.vendored_text),
            "file": target, "notice": notice,
        })
        text = (self.output / notice).read_text()
        self.assertIn("Provenance: release\n", text)
        self.assertNotIn("POST-RELEASE", text)
        self.assertNotIn("vendored", next(p for p in result["npm"]["packages"]
                                          if p["name"] == "alpha"))
        self.assertEqual(licenses.verify(self.output), result)

    def test_vendored_license_version_mismatch_fails(self):
        self.add_unlicensed_native(version="1.0.1")
        with self.assertRaisesRegex(ValueError, "No license text found.*native-x64"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_unlisted_package_without_license_still_fails(self):
        self.add_unlicensed_native(name="@scope/native-arm64")
        with self.assertRaisesRegex(ValueError, "No license text found.*native-arm64"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_vendored_license_declaration_mismatch_fails(self):
        self.add_unlicensed_native(license="ISC")
        with self.assertRaisesRegex(ValueError, "Vendored license declaration mismatch"):
            self.collect()

    def test_vendored_manifest_tamper_rejected(self):
        self.add_unlicensed_native()
        bad = (("sha256", "0" * 64, "digest mismatch"),
               ("release_commit", "main", "Invalid vendored"),
               ("license_commit", "C" * 40, "Invalid vendored"),
               ("provenance", "unknown", "provenance"),
               ("repository", "https://example.com/x/y", "Invalid vendored"),
               ("license", "UNKNOWN", "Unknown/unsupported"),
               ("file", "../LICENSE", "Unsafe path"))
        for field, value, message in bad:
            with self.subTest(field=field):
                self.save_vendored([{**self.vendored_entry, field: value}])
                with self.assertRaisesRegex(ValueError, message):
                    self.collect(self.root / f"tamper-{field}")
        self.save_vendored([self.vendored_entry, self.vendored_entry])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.collect(self.root / "duplicate")
        self.save_vendored()
        (self.vendored / self.vendored_entry["file"]).write_bytes(b"edited\n")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.collect(self.root / "edited")

    def test_checked_in_vendored_licenses_are_pinned(self):
        entries = licenses.vendored_licenses(Path(__file__).with_name("vendored-licenses"))
        platforms = {"android-arm64", "darwin-arm64", "darwin-x64", "linux-arm-gnueabihf",
                     "linux-arm64-gnu", "linux-arm64-musl", "linux-riscv64-gnu",
                     "linux-x64-gnu", "linux-x64-musl", "win32-arm64-msvc",
                     "win32-x64-msvc"}
        expected = {(f"@napi-rs/canvas-{p}", "0.1.100") for p in platforms}
        self.assertEqual(set(entries), expected | {("html-parse-stringify", "3.0.1"),
                                                   ("tr46", "0.0.3")})
        for identity in expected:
            entry = entries[identity][0]
            self.assertEqual(entry["repository"], "https://github.com/Brooooooklyn/canvas")
            self.assertEqual(entry["provenance"], "release")
            self.assertEqual(entry["release_commit"],
                             "db337893b9b53483050ca7b24c6d306e4da06741")
            self.assertEqual(entry["license_commit"], entry["release_commit"])
        post = {
            ("html-parse-stringify", "3.0.1"): (
                "https://github.com/henrikjoreteg/html-parse-stringify",
                "ce46022f537ef9b050fac592f9fcc30bf838e5ba",
                "a2659e6eac3603ba8b46958e0bd35b337108261f"),
            ("tr46", "0.0.3"): (
                "https://github.com/jsdom/tr46",
                "a8009f9ce80ff5dbe71dd71e203afe4e4c878d28",
                "3a6f29721e7063b9ffd421e461a54beae6170001"),
        }
        for identity, (repository, release, license_commit) in post.items():
            entry = entries[identity][0]
            self.assertEqual((entry["repository"], entry["provenance"],
                              entry["release_commit"], entry["license_commit"]),
                             (repository, "post-release", release, license_commit))
        for entry, _ in entries.values():
            self.assertEqual(entry["license"], "MIT")

    def test_post_release_label_in_record_and_notice(self):
        self.vendored_entry.update(provenance="post-release", license_commit="d" * 40)
        self.save_vendored()
        self.add_unlicensed_native()
        result = self.collect()
        record = next(p for p in result["npm"]["packages"]
                      if p["name"] == "@scope/native-x64")
        self.assertEqual(record["vendored"]["provenance"], "post-release")
        self.assertEqual(record["vendored"]["release_commit"], "c" * 40)
        self.assertEqual(record["vendored"]["license_commit"], "d" * 40)
        self.assertIn(record["vendored"]["notice"], record["files"])
        self.assertIn(record["vendored"]["notice"], result["files"])
        text = (self.output / record["vendored"]["notice"]).read_text()
        self.assertIn("@scope/native-x64@1.0.0 (declared license: MIT)", text)
        self.assertIn("Provenance: post-release\n", text)
        self.assertIn("POST-RELEASE", text)
        self.assertIn("license commit: " + "d" * 40, text)
        self.assertIn("released commit (npm gitHead): " + "c" * 40, text)
        self.assertEqual(licenses.verify(self.output), result)

    def test_provenance_must_agree_with_commits(self):
        self.add_unlicensed_native()
        for provenance, license_commit in (("post-release", "c" * 40),
                                           ("release", "d" * 40)):
            with self.subTest(provenance=provenance):
                self.save_vendored([{**self.vendored_entry, "provenance": provenance,
                                     "license_commit": license_commit}])
                with self.assertRaisesRegex(ValueError, "provenance"):
                    self.collect(self.root / f"prov-{provenance}")

    def test_vendored_text_must_match_declared_license(self):
        self.add_unlicensed_native()
        isc = (b"ISC License\n\nPermission to use, copy, modify, and/or distribute this "
               b"software for any purpose with or without fee is hereby granted.\n")
        for text in (isc, MIT_TEXT.replace(b"WITHOUT WARRANTY", b"WITH WARRANTY")):
            with self.subTest(text=text[:12]):
                self.vendored_text = text
                self.vendored_entry["sha256"] = licenses.sha256(text)
                self.save_vendored()
                with self.assertRaisesRegex(ValueError, "does not match MIT"):
                    self.collect(self.root / f"text-{len(text)}")
        self.assertFalse((self.output / "manifest.json").exists())

    def test_vendored_license_without_text_check_rejected(self):
        self.add_unlicensed_native(license="ISC")
        self.vendored_entry["license"] = "ISC"
        self.save_vendored()
        with self.assertRaisesRegex(ValueError, "does not match ISC"):
            self.collect()

    def test_go_vendored_license_used_for_exact_module_and_packages(self):
        result = self.collect()
        go_ignores = [a for a in self.calls if a[0][:2] == ["go", "run"]][0][0][5:-2]
        self.assertEqual(go_ignores, ["--ignore", "example.com/unknown",
                                      "--ignore", "example.com/unknown/sub"])
        self.assertEqual(result["go"]["command"][5:-2], go_ignores)
        self.assertEqual(result["go"]["vendored"], [{
            "module": "example.com/unknown", "version": "v1.2.3",
            "packages": ["example.com/unknown", "example.com/unknown/sub"],
            "license": "Apache-2.0", "provenance": "module",
            "sha256": licenses.sha256(self.go_text),
            "file": "go/example.com/unknown/LICENSE",
            "notice": "go/example.com/unknown/VENDORED-LICENSE-NOTICE.txt",
        }])
        self.assertEqual((self.output / "go/example.com/unknown/LICENSE").read_bytes(),
                         self.go_text)
        notice = (self.output / "go/example.com/unknown/VENDORED-LICENSE-NOTICE.txt").read_text()
        self.assertIn("example.com/unknown@v1.2.3", notice)
        self.assertIn("license: Apache-2.0\n", notice)
        self.assertIn("  example.com/unknown/sub\n", notice)
        self.assertIn("go/example.com/unknown/VENDORED-LICENSE-NOTICE.txt", result["files"])
        self.assertEqual(licenses.verify(self.output), result)

    def test_go_vendored_version_mismatch_fails(self):
        for version in ("v1.2.4", "v1.2.3-0.20200101000000-abcdefabcdef"):
            with self.subTest(version=version):
                self.go_build["example.com/unknown/sub"] = (
                    "example.com/unknown", version, str(self.go_module_dir), "")
                with self.assertRaisesRegex(ValueError, "version mismatch"):
                    self.collect(self.root / f"go-{version}")
                self.assertFalse(any(c[0][:2] == ["go", "run"] for c in self.calls))

    def test_go_replaced_module_fails(self):
        self.go_build["example.com/unknown"] = (
            "example.com/unknown", "v1.2.3", str(self.go_module_dir), "example.com/fork@v9.0.0")
        with self.assertRaisesRegex(ValueError, "version mismatch.*fork"):
            self.collect()

    def test_go_unlisted_unknown_module_still_fails(self):
        self.go_build["example.com/other"] = ("example.com/other", "v1.0.0", "/mod/other", "")
        self.go_unknown.append("example.com/other")
        with self.assertRaises(subprocess.CalledProcessError):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_go_new_package_in_vendored_module_still_fails(self):
        self.go_build["example.com/unknown2"] = (
            "example.com/unknown2", "v1.0.0", "/mod/unknown2", "")
        with self.assertRaisesRegex(ValueError, "ignored without a vendored entry: "
                                                "example.com/unknown2"):
            self.collect()
        self.go_build.pop("example.com/unknown2")
        self.go_build["example.com/unknown/sub/deeper"] = (
            "example.com/unknown", "v1.2.3", str(self.go_module_dir), "")
        with self.assertRaisesRegex(ValueError, "ignored without a vendored entry"):
            self.collect(self.root / "deeper")

    def test_go_listed_package_missing_from_build_fails(self):
        del self.go_build["example.com/unknown/sub"]
        with self.assertRaisesRegex(ValueError, "not in build: example.com/unknown/sub"):
            self.collect()

    def test_go_vendored_file_must_equal_module_file(self):
        (self.go_module_dir / "LICENSE").write_bytes(APACHE_HEADER + b"edited\n")
        with self.assertRaisesRegex(ValueError, "differs from module file"):
            self.collect()
        (self.go_module_dir / "LICENSE").unlink()
        with self.assertRaises(OSError):
            self.collect(self.root / "missing")

    def test_go_licenses_must_not_also_save_vendored_module(self):
        self.go_saves_vendored = True
        with self.assertRaisesRegex(ValueError, "also saved vendored Go module"):
            self.collect()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_go_public_domain_dedication_recorded_as_such(self):
        self.go_text = PUBLIC_DOMAIN_TEXT
        (self.go_module_dir / "LICENSE").write_bytes(self.go_text)
        self.go_entry.update(license="LicenseRef-public-domain",
                             sha256=licenses.sha256(self.go_text))
        self.save_vendored()
        result = self.collect()
        self.assertEqual(result["go"]["vendored"][0]["license"], "LicenseRef-public-domain")
        notice = (self.output / "go/example.com/unknown/VENDORED-LICENSE-NOTICE.txt").read_text()
        self.assertIn("public-domain dedication; not a license grant", notice)
        with self.assertRaises(ValueError):
            licenses.spdx("LicenseRef-public-domain")

    def test_go_vendored_text_must_match_license(self):
        for license, text in (("Apache-2.0", MIT_TEXT), ("MIT", APACHE_HEADER),
                              ("LicenseRef-public-domain", APACHE_HEADER),
                              ("Apache-2.0 OR MIT", APACHE_HEADER)):
            with self.subTest(license=license):
                self.go_text = text
                self.go_entry.update(license=license, sha256=licenses.sha256(text))
                self.save_vendored()
                with self.assertRaisesRegex(ValueError, "does not match"):
                    self.collect(self.root / f"go-text-{len(self.calls)}")

    def test_go_vendored_manifest_tamper_rejected(self):
        bad = (("provenance", "post-release", "provenance"),
               ("version", "latest", "Invalid vendored Go"),
               ("version", "v1.2", "Invalid vendored Go"),
               ("module", "Example.COM", "Invalid vendored Go"),
               ("packages", [], "Invalid vendored Go"),
               ("packages", ["example.com/unknownx"], "Invalid vendored Go"),
               ("packages", ["example.com/unknown/sub", "example.com/unknown"],
                "Invalid vendored Go"),
               ("license", "UNKNOWN", "Unknown/unsupported"),
               ("sha256", "0" * 64, "digest mismatch"),
               ("file", "../LICENSE", "Unsafe path"))
        for field, value, message in bad:
            with self.subTest(field=field, value=value):
                self.save_vendored(go_entries=[{**self.go_entry, field: value}])
                with self.assertRaisesRegex(ValueError, message):
                    self.collect(self.root / f"go-tamper-{len(self.calls)}")
        self.save_vendored(go_entries=[self.go_entry, self.go_entry])
        with self.assertRaisesRegex(ValueError, "Duplicate vendored Go license entry"):
            self.collect(self.root / "go-duplicate")
        other = {**self.go_entry, "module": "example.com/unknown/sub",
                 "packages": ["example.com/unknown/sub"]}
        self.save_vendored(go_entries=[self.go_entry, other])
        with self.assertRaisesRegex(ValueError, "Duplicate vendored Go package"):
            self.collect(self.root / "go-overlap")

    def test_no_go_entries_runs_without_ignores(self):
        self.save_vendored(go_entries=[])
        self.go_unknown = []
        result = self.collect()
        self.assertFalse(any(c[0][:3] == ["go", "list", "-deps"] for c in self.calls))
        self.assertEqual(result["go"]["vendored"], [])
        self.assertEqual(result["go"]["command"][5:], ["--save_path", "OUTPUT/go"])

    def test_checked_in_go_vendored_licenses_are_pinned(self):
        root = Path(__file__).with_name("vendored-licenses")
        entries = licenses.vendored_go_licenses(root)
        expected = {
            "github.com/cyberphone/json-canonicalization": (
                "v0.0.0-20241213102144-19d51d7fe467", "Apache-2.0",
                ["github.com/cyberphone/json-canonicalization/go/src/webpki.org/jsoncanonicalizer"]),
            "github.com/in-toto/attestation": ("v1.1.2", "Apache-2.0",
                                               ["github.com/in-toto/attestation/go/v1"]),
            "github.com/in-toto/in-toto-golang": ("v0.9.0", "Apache-2.0", [
                "github.com/in-toto/in-toto-golang/in_toto",
                "github.com/in-toto/in-toto-golang/in_toto/slsa_provenance/common",
                "github.com/in-toto/in-toto-golang/in_toto/slsa_provenance/v0.1",
                "github.com/in-toto/in-toto-golang/in_toto/slsa_provenance/v0.2",
                "github.com/in-toto/in-toto-golang/in_toto/slsa_provenance/v1"]),
            "github.com/jackpal/go-nat-pmp": ("v1.0.2", "Apache-2.0",
                                              ["github.com/jackpal/go-nat-pmp"]),
            "github.com/multiformats/go-base36": ("v0.2.0", "Apache-2.0 OR MIT",
                                                  ["github.com/multiformats/go-base36"]),
            "github.com/xi2/xz": ("v0.0.0-20171230120015-48954b6210f8",
                                  "LicenseRef-public-domain", ["github.com/xi2/xz"]),
        }
        self.assertEqual({m: (e["version"], e["license"], e["packages"])
                          for m, (e, _) in entries.items()}, expected)
        for entry, _ in entries.values():
            self.assertEqual(entry["provenance"], "module")

    def test_metadata_tamper(self):
        path = self.ui / "node_modules/alpha/package.json"
        metadata = json.loads(path.read_text())
        for field, value in (("version", "9.0.0"), ("name", "impostor"),
                             ("license", "ISC"), ("dependencies", {})):
            with self.subTest(field=field):
                path.write_text(json.dumps({**metadata, field: value}))
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    self.collect(self.root / f"bad-{field}")

    def test_lock_v3_required(self):
        (self.ui / "package-lock.json").write_text('{"lockfileVersion":2}')
        with self.assertRaisesRegex(ValueError, "v3"):
            self.collect()

    def test_dev_only_excluded_even_if_installed_without_legal_files(self):
        path = self.ui / "node_modules/dev"
        path.mkdir()
        (path / "package.json").write_text('{"license":"UNKNOWN"}')
        self.assertFalse(any("node_modules/dev/" in p for p in self.collect()["files"]))

    def test_nested_resolution_and_required_peer(self):
        self.add_package("node_modules/alpha/node_modules/@scope/beta",
                         name="@scope/beta", version="2.0.0")
        # The hoisted beta is still needed by an installed optional package.
        self.packages["node_modules/optional"]["peerDependencies"] = {"@scope/beta": "*"}
        metadata = self.ui / "node_modules/optional/package.json"
        data = json.loads(metadata.read_text())
        data["peerDependencies"] = {"@scope/beta": "*"}
        metadata.write_text(json.dumps(data))
        self.save_lock()
        self.assertEqual(len(self.collect()["npm"]["packages"]), 4)

    def test_unreachable_nondev_dependency_rejected(self):
        self.add_package("node_modules/orphan")
        self.save_lock()
        with self.assertRaisesRegex(ValueError, "unreachable"):
            self.collect()

    def test_unsafe_lock_paths_rejected(self):
        for key in ("../escape", "/absolute", "node_modules/../escape",
                    r"node_modules\escape", "node_modules/C:escape", "node_modules",
                    "node_modules/NUL.txt", "node_modules/bad.", "node_modules/bad*"):
            with self.subTest(key=key):
                self.packages[key] = {"dev": True}
                self.save_lock()
                with self.assertRaises(ValueError):
                    self.collect(self.root / f"bad-{len(self.calls)}")
                del self.packages[key]

    def test_symlink_license_and_package_escape_rejected(self):
        path = self.ui / "node_modules/alpha/LICENSE"
        path.unlink()
        path.symlink_to(self.source / "LICENSE")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.collect()

    def test_symlink_package_ancestor_rejected(self):
        import shutil
        scope = self.ui / "node_modules/@scope"
        moved = self.root / "scope"
        shutil.move(scope, moved)
        scope.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.collect()

    def test_output_must_be_new_and_outside_source(self):
        for output in (self.source / "licenses", self.source, self.root):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.collect(output)
        self.collect()
        with self.assertRaisesRegex(ValueError, "already exist"):
            self.collect()

    def test_notice_tree_and_multiple_license_files_preserved(self):
        package = self.ui / "node_modules/alpha"
        (package / "legal/licenses").mkdir(parents=True)
        (package / "legal/licenses/vendor.txt").write_bytes(b"Original vendor license\n")
        (package / "COPYING.BSD").write_bytes(b"Original BSD legal text\n")
        (package / "ThirdPartyNoticeText.txt").write_bytes(b"Vendor notices\n")
        manifest = self.collect()
        self.assertIn("npm/node_modules/alpha/legal/licenses/vendor.txt", manifest["files"])
        self.assertIn("npm/node_modules/alpha/COPYING.BSD", manifest["files"])
        self.assertIn("npm/node_modules/alpha/ThirdPartyNoticeText.txt", manifest["files"])

    def test_empty_legal_file_rejected(self):
        (self.ui / "node_modules/alpha/NOTICE").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "Empty legal"):
            self.collect()

    def test_cgo_enabled_rejected(self):
        with patch.dict(os.environ, {"CGO_ENABLED": "1"}), \
                self.assertRaisesRegex(ValueError, "CGO_ENABLED=0"):
            licenses.collect(self.source, self.output)

    def test_output_symlink_ancestor_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlink output"):
            self.collect(alias / "licenses")

    def test_nonportable_and_case_colliding_inventory_rejected(self):
        if os.name == "nt":
            self.skipTest("Windows rejects the nonportable fixture name at creation")
        self.collect()
        (self.output / "bad\\name").write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            licenses.verify(self.output)
        (self.output / "bad\\name").unlink()
        # Also works on case-insensitive hosts: a differently-cased directory and
        # its child create a collision after portable case folding.
        with patch.object(licenses.os, "walk", return_value=[
                (str(self.output), ["Go", "go"], [])]), \
                self.assertRaisesRegex(ValueError, "Case-colliding"):
            licenses.inventory(self.output)

    def test_go_failure_never_commits_manifest(self):
        def fail(args, cwd, env=None):
            if args[:2] == ["go", "run"]:
                raise subprocess.CalledProcessError(1, args)
            return self.mock_run(args, cwd, env)
        with patch.object(licenses, "run", side_effect=fail), \
                self.assertRaises(subprocess.CalledProcessError):
            licenses.collect(self.source, self.output)
        self.assertFalse((self.output / "manifest.json").exists())

    def test_wrong_or_missing_tool_origin_rejected(self):
        for origin in ({}, {"Hash": "b" * 40}):
            def wrong(args, cwd, env=None):
                data = self.mock_run(args, cwd, env)
                if args[:2] == ["go", "mod"]:
                    identity = json.loads(data)
                    identity["Origin"] = origin
                    return json.dumps(identity).encode()
                return data
            with self.subTest(origin=origin), \
                    patch.object(licenses, "run", side_effect=wrong), \
                    self.assertRaisesRegex(ValueError, "tool identity"):
                licenses.collect(self.source, self.output)
            self.assertFalse(self.output.exists())

    def test_inventory_detects_modified_missing_added_and_symlink_files(self):
        self.collect()
        path = self.output / "npm/node_modules/alpha/LICENSE"
        original = path.read_bytes()
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            licenses.verify(self.output)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            licenses.verify(self.output)
        path.write_bytes(original)
        extra = self.output / "extra"
        extra.write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            licenses.verify(self.output)
        extra.unlink()
        path.unlink()
        path.symlink_to(self.source / "LICENSE")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            licenses.verify(self.output)

    def test_empty_go_output_rejected(self):
        def empty(args, cwd, env=None):
            return b"" if args[:2] == ["go", "run"] else self.mock_run(args, cwd, env)
        with patch.object(licenses, "run", side_effect=empty), \
                self.assertRaisesRegex(ValueError, "no legal materials"):
            licenses.collect(self.source, self.output)
        self.assertFalse((self.output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
