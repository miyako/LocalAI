import contextlib
import io
import json
import shutil
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import component


class CompileGuardTests(unittest.TestCase):
    def test_require_structured_success_and_no_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "compile.json"
            report.write_text(json.dumps({"success": True, "errors": []}))
            component.validate_report(report)
            for value in ({"success": False, "errors": []}, {"success": True},
                          {"success": True, "errors": [{"message": "warning"}]},
                          {"success": "true", "errors": []}):
                report.write_text(json.dumps(value))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    component.validate_report(report)

    def test_compiled_archive_accepts_both_filename_casings_and_rejects_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            product = Path(temp)
            with self.assertRaises(ValueError):
                component.validate_archive(product)
            for extension in (".4DZ", ".4dz"):
                archive = product / ("LocalAI" + extension)
                with zipfile.ZipFile(archive, "w") as file:
                    file.writestr("compiled-code", "fixture")
                component.validate_archive(product)
                archive.unlink()
            (product / "LocalAI.4DZ").write_bytes(b"not a zip")
            with self.assertRaises(zipfile.BadZipFile):
                component.validate_archive(product)

    def test_guard_invocation_requires_real_report_and_cleans_temporary_method(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compiler = root / "compiler"
            methods = compiler / "Project/Sources/Methods"
            methods.mkdir(parents=True)
            project = root / "LocalAI.4DProject"
            project.write_text("{}")
            product = root / "product"
            product.mkdir()
            with zipfile.ZipFile(product / "LocalAI.4DZ", "w") as archive:
                archive.writestr("compiled-code", "fixture")
            def invoke(args, **kwargs):
                settings = json.loads(next(arg.removeprefix("--user-param=")
                                           for arg in args if arg.startswith("--user-param=")))
                self.assertEqual(settings["project"], str(project.resolve()))
                self.assertEqual(settings["components"], [])
                Path(settings["report"]).write_text('{"success":true,"errors":[]}')
            with patch.object(component.subprocess, "run", side_effect=invoke), \
                    contextlib.redirect_stdout(io.StringIO()):
                component.check(project, product, compiler, root / "tool4d")
            self.assertFalse((methods / "native_validate_component.4dm").exists())


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "Project/LocalAI.4DProject"
        (self.root / "Project/Sources").mkdir(parents=True)
        self.project.write_text("{}")
        self.work = self.root / "work"
        self.work.mkdir()
        self.releases = {}
        self.archives = {}

    def tearDown(self):
        self.temp.cleanup()

    def declare(self, dependencies):
        (self.root / "Project/Sources/dependencies.json").write_text(
            json.dumps({"version": 2100, "dependencies": dependencies}))

    def publish(self, repository, name, tag="1.0.0", members=None, **release):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for member, data in (members or {f"{name}.4dbase/{name}.4DZ": b"compiled"}).items():
                archive.writestr(member, data)
        self.archives[(repository, 7)] = buffer.getvalue()
        self.releases[f"repos/{repository}/releases/latest"] = {
            "tag_name": tag, "draft": False, "prerelease": False,
            "assets": [{"name": f"{name}.zip", "id": 7}], **release}

    def fetch(self):
        def downloader(repository, asset, path):
            path.write_bytes(self.archives[(repository, asset["id"])])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = component.dependencies(self.project, self.work,
                                            lookup=self.releases.__getitem__,
                                            downloader=downloader)
        return result, out.getvalue()

    def test_no_manifest_means_no_components(self):
        self.assertEqual(self.fetch()[0], [])

    def test_latest_github_release_is_extracted_and_logged(self):
        self.declare({"event": {"github": "miyako/event", "version": "latest"}})
        self.publish("miyako/event", "event", tag="20.0.19")
        components, log = self.fetch()
        expected = (self.work / "Components/event.4dbase/event.4DZ").resolve()
        self.assertEqual(components, [str(expected)])
        self.assertEqual(expected.read_bytes(), b"compiled")
        self.assertIn("miyako/event@20.0.19", log)

    def test_rejects_unsupported_or_unsafe_dependencies(self):
        cases = (
            ({"event": {"path": "../event"}}, None, "Unsupported"),
            ({"../x": {"github": "miyako/x"}}, None, "Unsupported"),
            ({"event": {"github": "miyako/event"}}, {"prerelease": True}, "stable"),
            ({"event": {"github": "miyako/event"}}, {"assets": []}, "single event.zip"),
            ({"event": {"github": "miyako/event"}},
             {"members": {"../evil": b"x"}}, "Unexpected path"),
            ({"event": {"github": "miyako/event"}},
             {"members": {"event.4dbase/other.txt": b"x"}}, "no compiled"),
        )
        for dependencies, release, message in cases:
            with self.subTest(dependencies=dependencies, release=release):
                self.declare(dependencies)
                release = dict(release or {})
                self.publish("miyako/event", "event", members=release.pop("members", None),
                             **release)
                shutil.rmtree(self.work)
                self.work.mkdir()
                with self.assertRaisesRegex(ValueError, message):
                    self.fetch()
