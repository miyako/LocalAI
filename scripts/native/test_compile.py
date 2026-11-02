import contextlib
import io
import json
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
                Path(settings["report"]).write_text('{"success":true,"errors":[]}')
            with patch.object(component.subprocess, "run", side_effect=invoke), \
                    contextlib.redirect_stdout(io.StringIO()):
                component.check(project, product, compiler, root / "tool4d")
            self.assertFalse((methods / "native_validate_component.4dm").exists())
