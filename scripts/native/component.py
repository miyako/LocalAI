#!/usr/bin/env python3
"""Independently require a structured 4D compile result and a real compiled archive."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import re
import tempfile
import urllib.parse
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


def api(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True, timeout=120))


def download(repository, asset, path):
    with path.open("xb") as out:
        subprocess.run(["gh", "api", f"repos/{repository}/releases/assets/{asset['id']}",
                        "-H", "Accept: application/octet-stream"],
                       stdout=out, check=True, timeout=600)


def dependencies(project, directory, lookup=api, downloader=download):
    """Fetch the compiled components the project declares, as the 4D dependency manager does.

    Only GitHub release dependencies are supported. Each must ship NAME.zip holding
    NAME.4dbase/NAME.4DZ. Resolved release tags are printed for the build log.
    """
    manifest = project.parent / "Sources/dependencies.json"
    if not manifest.is_file():
        return []
    declared = json.loads(manifest.read_text(encoding="utf-8-sig")).get("dependencies", {})
    if not isinstance(declared, dict):
        raise ValueError("Invalid dependencies.json")
    components = []
    for name, spec in sorted(declared.items()):
        repository = spec.get("github") if isinstance(spec, dict) else None
        version = spec.get("version", "latest") if isinstance(spec, dict) else None
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
                or not isinstance(repository, str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                or not isinstance(version, str) or not version):
            raise ValueError(f"Unsupported component dependency declaration: {name}")
        endpoint = "releases/latest" if version == "latest" else (
            "releases/tags/" + urllib.parse.quote(version, safe=""))
        release = lookup(f"repos/{repository}/{endpoint}")
        if release.get("draft") is not False or release.get("prerelease") is not False:
            raise ValueError(f"Dependency release must be published and stable: {name}")
        assets = [a for a in release.get("assets", []) if a.get("name") == name + ".zip"]
        if len(assets) != 1:
            raise ValueError(f"Dependency release has no single {name}.zip asset: {repository}")
        archive = directory / (name + ".zip")
        downloader(repository, assets[0], archive)
        root = directory / "Components"
        with zipfile.ZipFile(archive) as content:
            for member in content.namelist():
                path = Path(member)
                if path.is_absolute() or ".." in path.parts or path.parts[0] != name + ".4dbase":
                    raise ValueError(f"Unexpected path in dependency archive {name}: {member}")
            content.extractall(root)
        compiled = root / (name + ".4dbase") / (name + ".4DZ")
        if not compiled.is_file() or compiled.stat().st_size == 0:
            raise ValueError(f"Dependency archive has no compiled {name}.4DZ")
        print(f"Dependency {name}: {repository}@{release.get('tag_name')} ({version})")
        components.append(str(compiled.resolve()))
    return components


def check(project, product, compiler, tool):
    method = compiler / "Project/Sources/Methods/native_validate_component.4dm"
    if method.exists():
        raise ValueError("Compiler validation method path is already occupied")
    shutil.copyfile(Path(__file__).with_name("validate_component.4dm"), method)
    try:
        with tempfile.TemporaryDirectory(prefix="localai-compile-") as temp:
            report = Path(temp) / "compile.json"
            components = dependencies(project, Path(temp))
            subprocess.run(
                [str(tool.resolve()), str((compiler / "Project/compiler.4DProject").resolve()),
                 "--skip-onstartup", "--startup-method=native_validate_component",
                 "--user-param=" + json.dumps({"project": str(project.resolve()), "report": str(report),
                                               "components": components}),
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
