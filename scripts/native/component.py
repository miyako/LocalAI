#!/usr/bin/env python3
"""Independently require a structured 4D compile result and a real compiled archive."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def validate_report(path):
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    if report.get("success") is not True or report.get("errors") != []:
        raise ValueError("4D compilation did not succeed without diagnostics: " + json.dumps(report))


def validate_archive(product):
    archives = [path for path in product.rglob("*")
                if path.is_file() and path.suffix.lower() == ".4dz"]
    if len(archives) != 1 or archives[0].stat().st_size == 0:
        raise ValueError("Expected exactly one nonempty compiled .4DZ/.4dz archive")
    with zipfile.ZipFile(archives[0]) as archive:
        if not archive.namelist() or archive.testzip() is not None:
            raise ValueError("Invalid compiled standard-ZIP component archive")


def check(project, product, compiler, tool):
    method = compiler / "Project/Sources/Methods/native_validate_component.4dm"
    if method.exists():
        raise ValueError("Compiler validation method path is already occupied")
    shutil.copyfile(Path(__file__).with_name("validate_component.4dm"), method)
    try:
        with tempfile.TemporaryDirectory(prefix="localai-compile-") as temp:
            report = Path(temp) / "compile.json"
            subprocess.run(
                [str(tool.resolve()), str((compiler / "Project/compiler.4DProject").resolve()),
                 "--skip-onstartup", "--startup-method=native_validate_component",
                 "--user-param=" + json.dumps({"project": str(project.resolve()), "report": str(report)}),
                 "--dataless"], check=True, timeout=600)
            validate_report(report)
        validate_archive(product)
    finally:
        method.unlink()
    print("Structured 4D compile succeeded without diagnostics; compiled archive verified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, default=Path("compiler"))
    parser.add_argument("--tool", type=Path, default=Path("tool4d.app/Contents/MacOS/tool4d"))
    args = parser.parse_args()
    check(args.project, args.product, args.compiler, args.tool)


if __name__ == "__main__":
    main()
