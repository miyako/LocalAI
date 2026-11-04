#!/usr/bin/env python3
"""Collect native CLI/UI legal materials without modifying the checkout.

Usage: python3 licenses.py UPSTREAM_CHECKOUT OUTPUT_DIR

OUTPUT_DIR must not exist and must be outside the checkout. Ship the entire
directory, including manifest.json, LICENSE-LocalAI, go/ and npm/. The manifest
inventories every file except itself. verify() checks that inventory exactly.

The npm SPDX vocabulary below is deliberately conservative, not a legal policy:
unsupported declarations fail rather than being inferred from package contents.
New identifiers require explicit review. License text is never synthesized.

A package that ships no license text fails, unless vendored-licenses/manifest.json
lists its exact name and version. Each such entry pins the upstream repository,
the released commit (npm gitHead), the commit the real LICENSE file comes from
and its sha256. provenance is "release" when both commits are the same, or
"post-release" when upstream added the file only after that release. The text
must match the declared license; a generated notice records the provenance.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys


GO_MODULE = "github.com/google/go-licenses/v2"
GO_VERSION = "v2.0.1"
GO_COMMIT = "3e084b0caf710f7bfead967567539214f598c0a2"
UI = "core/http/react-ui"
VENDORED = Path(__file__).resolve().with_name("vendored-licenses")
PUBLIC_DOMAIN = "LicenseRef-public-domain"
# Declared licenses whose vendored text can be checked; others are rejected.
LICENSE_TEXT = {
    "MIT": ("Permission is hereby granted, free of charge, to any person obtaining a copy "
            "of this software and associated documentation files (the \"Software\"), to deal "
            "in the Software without restriction",
            "The above copyright notice and this permission notice shall be included in all "
            "copies or substantial portions of the Software.",
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND"),
    # Short Apache header form (no full text) that go-licenses cannot classify.
    "Apache-2.0": ("Licensed under the Apache License, Version 2.0 (the \"License\"); "
                   "you may not use this file except in compliance with the License.",
                   "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND"),
    "Apache-2.0 OR MIT": ("Apache-2.0 Software License", "MIT Software License",
                          "SPDX-License-Identifier: Apache-2.0 OR MIT"),
    # A public-domain dedication is not a license grant and has no SPDX identifier.
    PUBLIC_DOMAIN: ("have been put into the public domain",),
}
VENDORED_NOTICE = "VENDORED-LICENSE-NOTICE.txt"
GO_PACKAGE = "./cmd/local-ai"
GO_MODULE_VERSION = re.compile(
    r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+incompatible)?")
SPDX_IDS = frozenset("""
0BSD MIT ISC Apache-2.0 BSD-2-Clause BSD-3-Clause BSD-4-Clause
CC0-1.0 CC-BY-3.0 CC-BY-4.0 Unlicense WTFPL Zlib Python-2.0
Artistic-2.0 BlueOak-1.0.0 BSL-1.0 MPL-2.0 EPL-1.0 EPL-2.0 OFL-1.1
LGPL-2.0-only LGPL-2.0-or-later LGPL-2.1-only LGPL-2.1-or-later
LGPL-3.0-only LGPL-3.0-or-later GPL-2.0-only GPL-2.0-or-later
GPL-3.0-only GPL-3.0-or-later AGPL-3.0-only AGPL-3.0-or-later
""".split())
LEGAL = re.compile(
    r"^(?:licen[cs]es?|copying|notices?|copyright|"
    r"third[-_ ]?party[-_ ]?(?:notices?|licen[cs]es?)(?:text)?)"
    r"(?:[._ -].*)?$", re.I)
LICENSE = re.compile(r"^(?:licen[cs]e|copying)(?:[._ -].*)?$", re.I)


def run(args, cwd, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def relative(value):
    """Validate portable, unambiguous archive-relative paths."""
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(c) < 32 for c in value)):
        raise ValueError(f"Unsafe path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError(f"Unsafe path: {value!r}")
    for part in path.parts:
        if (any(c in part for c in '<>"|?*') or part.endswith((".", " "))
                or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",
                                part, re.I)):
            raise ValueError(f"Nonportable path: {value!r}")
    return path


def safe_path(root, value):
    path = root
    for part in relative(value).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Symlink not permitted: {path}")
    return path


def read_file(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Expected regular file: {path}")
    return path.read_bytes()


def read_json(path):
    return json.loads(read_file(path))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True)
                      + "\n").encode())


def copy_bytes(source, destination):
    data = read_file(source)
    if not data.strip():
        raise ValueError(f"Empty legal/metadata file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def spdx(expression):
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError(f"Missing npm license declaration: {expression!r}")
    tokens = re.findall(r"[A-Za-z0-9.+-]+|[()]", expression)
    if re.sub(r"\s+", "", expression) != "".join(tokens):
        raise ValueError(f"Unsupported license declaration: {expression!r}")
    position = 0

    def term():
        nonlocal position
        if position >= len(tokens):
            raise ValueError("Incomplete SPDX expression")
        token = tokens[position]
        position += 1
        if token == "(":
            clause()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("Unbalanced SPDX expression")
            position += 1
        elif token not in SPDX_IDS:
            raise ValueError(f"Unknown/unsupported SPDX license: {token}")

    def clause():
        nonlocal position
        term()
        while position < len(tokens) and tokens[position] in ("AND", "OR"):
            position += 1
            term()

    clause()
    if position != len(tokens):
        raise ValueError(f"Invalid SPDX expression: {expression!r}")
    return expression


def package_key(key):
    parts = relative(key).parts
    index = 0
    while index < len(parts):
        if parts[index] != "node_modules":
            raise ValueError(f"Invalid npm installation path: {key}")
        index += 1
        if index >= len(parts):
            raise ValueError(f"Invalid npm installation path: {key}")
        if parts[index].startswith("@"):
            index += 1
            if index >= len(parts):
                raise ValueError(f"Invalid scoped npm path: {key}")
        index += 1
    return key


def dependency_name(name):
    relative(name)
    parts = name.split("/")
    if not ((len(parts) == 1 and not name.startswith("@"))
            or (len(parts) == 2 and parts[0].startswith("@") and len(parts[0]) > 1)):
        raise ValueError(f"Invalid npm dependency name: {name}")
    return name


def legal_files(package):
    result = []
    for directory, dirs, files in os.walk(package, followlinks=False):
        dirs.sort()
        files.sort()
        for name in dirs + files:
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"Symlink in npm package: {Path(directory) / name}")
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
        for name in files:
            path = Path(directory) / name
            rel = path.relative_to(package)
            if LEGAL.match(name) or any(
                    p.lower() in ("license", "licenses", "licence", "licences")
                    for p in rel.parts[:-1]):
                result.append((rel.as_posix(), path))
    return sorted(result)


def has_license_text(files):
    return any(LICENSE.match(PurePosixPath(name).name)
               or any(p.lower() in ("licenses", "licences")
                      for p in PurePosixPath(name).parts[:-1]) for name, _ in files)


def vendored_licenses(root=None):
    """Load reviewed upstream LICENSE files for exact npm name+version entries."""
    root = Path(root or VENDORED)
    manifest = read_json(safe_path(root, "manifest.json"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("packages"), list):
        raise ValueError("Invalid vendored license manifest")
    keys = {"name", "version", "license", "repository", "provenance", "release_commit",
            "license_commit", "source_path", "file", "sha256"}
    result = {}
    for entry in manifest["packages"]:
        if not isinstance(entry, dict) or set(entry) != keys:
            raise ValueError(f"Invalid vendored license entry: {entry!r}")
        dependency_name(entry["name"])
        relative(entry["source_path"])
        if (not isinstance(entry["version"], str) or not entry["version"]
                or not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+",
                                    entry["repository"])
                or not all(re.fullmatch(r"[a-f0-9]{40}", entry[k])
                           for k in ("release_commit", "license_commit"))
                or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                or spdx(entry["license"]) != entry["license"]):
            raise ValueError(f"Invalid vendored license entry: {entry['name']}")
        same = entry["release_commit"] == entry["license_commit"]
        if entry["provenance"] not in ("release", "post-release") or same != (
                entry["provenance"] == "release"):
            raise ValueError(f"Invalid vendored license provenance: {entry['name']}")
        identity = (entry["name"], entry["version"])
        if identity in result:
            raise ValueError(f"Duplicate vendored license entry: {identity}")
        result[identity] = (entry, vendored_file(root, entry))
    return result


def vendored_file(root, entry):
    """Check a vendored file's pinned digest and that it matches its declared license."""
    path = safe_path(root, entry["file"])
    data = read_file(path)
    if not data.strip() or sha256(data) != entry["sha256"]:
        raise ValueError(f"Vendored license digest mismatch: {entry['file']}")
    phrases = LICENSE_TEXT.get(entry["license"])
    text = " ".join(data.decode("utf-8", "replace").split())
    if phrases is None or not all(phrase in text for phrase in phrases):
        raise ValueError(f"Vendored license text does not match {entry['license']}: "
                         f"{entry['file']}")
    return path


def vendored_go_licenses(root=None):
    """Load module-owned license files go-licenses cannot classify.

    Entries are keyed to an exact module path+version and the exact package paths
    go-licenses reports. Only those packages are passed to --ignore.
    """
    root = Path(root or VENDORED)
    manifest = read_json(safe_path(root, "manifest.json"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("go_modules"), list):
        raise ValueError("Invalid vendored license manifest")
    keys = {"module", "version", "packages", "license", "provenance", "source_path",
            "file", "sha256"}
    # A reviewed exception for a module with no license file anywhere upstream: the
    # classification rests on an exact README statement, vendored as an excerpt.
    readme_keys = keys | {"repository", "commit", "source_sha256", "statement",
                          "statement_line"}
    result = {}
    owners = {}
    for entry in manifest["go_modules"]:
        readme = isinstance(entry, dict) and entry.get("provenance") == "readme-statement"
        if not isinstance(entry, dict) or set(entry) != (readme_keys if readme else keys):
            raise ValueError(f"Invalid vendored Go license entry: {entry!r}")
        module = entry["module"]
        relative(module)
        relative(entry["source_path"])
        packages = entry["packages"]
        if (not re.fullmatch(r"[a-z0-9.-]+\.[a-z]+(?:/[\w.-]+)+", module)
                or not isinstance(entry["version"], str)
                or not GO_MODULE_VERSION.fullmatch(entry["version"])
                or not isinstance(packages, list) or not packages
                or packages != sorted(set(packages))
                or not all(isinstance(p, str) and (p == module or p.startswith(module + "/"))
                           for p in packages)
                or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                or (entry["license"] != PUBLIC_DOMAIN
                    and spdx(entry["license"]) != entry["license"])):
            raise ValueError(f"Invalid vendored Go license entry: {module}")
        # The file must be the module's own; upstream/post-release text is not supported.
        if entry["provenance"] not in ("module", "readme-statement"):
            raise ValueError(f"Invalid vendored Go license provenance: {module}")
        if readme:
            pseudo = re.search(r"-\d{14}-([a-f0-9]{12})$", entry["version"])
            if (not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", entry["repository"])
                    or not re.fullmatch(r"[a-f0-9]{40}", entry["commit"])
                    or (pseudo and not entry["commit"].startswith(pseudo.group(1)))
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["source_sha256"])
                    or entry["statement"] != entry["license"]
                    or entry["license"] not in SPDX_IDS
                    or not isinstance(entry["statement_line"], int)
                    or isinstance(entry["statement_line"], bool)
                    or entry["statement_line"] < 1):
                raise ValueError(f"Invalid vendored Go README statement entry: {module}")
        if module in result:
            raise ValueError(f"Duplicate vendored Go license entry: {module}")
        for package in packages:
            relative(package)
            if package in owners:
                raise ValueError(f"Duplicate vendored Go package: {package}")
            owners[package] = module
        result[module] = (entry, readme_excerpt(root, entry) if readme
                          else vendored_file(root, entry))
    return result


def readme_excerpt(root, entry):
    """Check a vendored README excerpt states exactly the recorded license."""
    path = safe_path(root, entry["file"])
    data = read_file(path)
    if not data.strip() or sha256(data) != entry["sha256"]:
        raise ValueError(f"Vendored license digest mismatch: {entry['file']}")
    lines = data.decode("utf-8").splitlines()
    if (entry["statement"] not in lines
            or not any(re.fullmatch(r"#+\s*licen[cs]e\s*", line, re.I) for line in lines)):
        raise ValueError(f"README excerpt does not state {entry['license']}: {entry['file']}")
    return path


def vendored_go_empty_files(root=None):
    """Load exact module@version files that go-licenses may copy as empty source files."""
    root = Path(root or VENDORED)
    manifest = read_json(safe_path(root, "manifest.json"))
    if not isinstance(manifest.get("go_empty_files"), list):
        raise ValueError("Invalid vendored license manifest")
    result = {}
    for entry in manifest["go_empty_files"]:
        if (not isinstance(entry, dict) or set(entry) != {"module", "version", "path"}
                or not isinstance(entry["module"], str)
                or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]+(?:/[\w.-]+)+", entry["module"])
                or not isinstance(entry["version"], str)
                or not GO_MODULE_VERSION.fullmatch(entry["version"])):
            raise ValueError(f"Invalid allowed empty Go file entry: {entry!r}")
        relative(entry["path"])
        key = f"go/{entry['module']}/{entry['path']}"
        relative(key)
        if key in result:
            raise ValueError(f"Duplicate allowed empty Go file: {key}")
        result[key] = entry
    return result


def go_build(source, env):
    listing = run(["go", "list", "-deps", "-f",
                   "{{.ImportPath}}\t{{with .Module}}{{.Path}}\t{{.Version}}\t{{.Dir}}"
                   "\t{{with .Replace}}{{.Path}}@{{.Version}}{{end}}{{end}}", GO_PACKAGE],
                  source, env).decode()
    build = {}
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) == 5:
            build[fields[0]] = fields[1:]
    return build


def go_empty_files(build, allowed):
    """Each allowed empty file must belong to a built, unreplaced module@version."""
    modules = {}
    for module, version, directory, replace in build.values():
        modules.setdefault(module, set()).add((version, directory, replace))
    for key, entry in sorted(allowed.items()):
        found = modules.get(entry["module"], set())
        versions = sorted(v for v, _, _ in found)
        if versions != [entry["version"]]:
            raise ValueError(f"Allowed empty Go file module version mismatch: {key}: "
                             f"{versions or 'not in build'}")
        version, directory, replace = next(iter(found))
        if replace or not directory:
            raise ValueError(f"Allowed empty Go file module is replaced/unavailable: {key}")
        original = safe_path(Path(directory), entry["path"])
        if read_file(original) != b"":
            raise ValueError(f"Allowed empty Go file is not empty in module: {key}")


def go_ignores(build, vendored):
    """Verify the build's exact Go packages/modules before trusting vendored files."""
    ignores = sorted(p for entry, _ in vendored.values() for p in entry["packages"])
    for package, (module, version, directory, replace) in sorted(build.items()):
        # go-licenses --ignore is a prefix match: nothing unlisted may be covered.
        if package not in ignores and any(package.startswith(i) for i in ignores):
            raise ValueError(f"Go package would be ignored without a vendored entry: {package}")
    for module, (entry, vendored_path) in sorted(vendored.items()):
        for package in entry["packages"]:
            if package not in build:
                raise ValueError(f"Vendored Go package not in build: {package}")
            path, version, directory, replace = build[package]
            if path != module or version != entry["version"] or replace:
                raise ValueError(f"Vendored Go module version mismatch: {package}: "
                                 f"{path}@{version}{' => ' + replace if replace else ''}")
            if not directory:
                raise ValueError(f"Go module directory unavailable: {module}")
            original = safe_path(Path(directory), entry["source_path"])
            if entry["provenance"] == "readme-statement":
                readme = read_file(original)
                lines = readme.decode("utf-8").splitlines()
                excerpt = read_file(vendored_path)
                if (sha256(readme) != entry["source_sha256"] or excerpt not in readme
                        or len(lines) < entry["statement_line"]
                        or lines[entry["statement_line"] - 1] != entry["statement"]):
                    raise ValueError(f"Go module README differs from reviewed statement: "
                                     f"{module}")
                shipped = [n for n in os.listdir(directory) if LEGAL.match(n)]
                if shipped:
                    raise ValueError(f"Go module now ships legal files; README exception "
                                     f"no longer applies: {module}: {shipped}")
            elif sha256(read_file(original)) != entry["sha256"]:
                raise ValueError(f"Vendored Go license differs from module file: {module}")
    return ignores


def vendored_go_notice(entry):
    label = entry["license"]
    if label == PUBLIC_DOMAIN:
        label += " (public-domain dedication; not a license grant)"
    name = PurePosixPath(entry["file"]).name
    if entry["provenance"] == "readme-statement":
        return "\n".join([
            f"{entry['module']}@{entry['version']}: NO LICENSE FILE exists in this module "
            "or anywhere in its upstream repository.",
            f"The {entry['license']} classification comes only from a statement in the "
            "upstream README, accepted as a reviewed exception:",
            f"  repository: {entry['repository']}",
            f"  commit: {entry['commit']}",
            f"  path: {entry['source_path']} (sha256 {entry['source_sha256']})",
            f"  statement (line {entry['statement_line']}): {entry['statement']}",
            f"{name} is an unmodified excerpt of that README (sha256 {entry['sha256']}); "
            "no license text was synthesized.",
            f"Provenance: {entry['provenance']}",
            "Packages excluded from go-licenses with --ignore after the README digest "
            "was verified:",
            *(f"  {p}" for p in entry["packages"]),
        ]) + "\n"
    return "\n".join([
        f"{entry['module']}@{entry['version']}: go-licenses {GO_VERSION} could not "
        "classify this module's license file.",
        f"{entry['source_path']} is the module's own unmodified file at that version.",
        f"  license: {label}",
        f"  sha256: {entry['sha256']}",
        f"Provenance: {entry['provenance']}",
        "Packages excluded from go-licenses with --ignore after the digest was verified:",
        *(f"  {p}" for p in entry["packages"]),
    ]) + "\n"


def vendored_notice(name, version, declaration, entry):
    lines = [
        f"{name}@{version} (declared license: {declaration}) ships no license text.",
        "LICENSE.vendored is the unmodified upstream file:",
        f"  repository: {entry['repository']}",
        f"  path: {entry['source_path']}",
        f"  license commit: {entry['license_commit']}",
        f"  released commit (npm gitHead): {entry['release_commit']}",
        f"  sha256: {entry['sha256']}",
        f"Provenance: {entry['provenance']}",
    ]
    if entry["provenance"] == "post-release":
        lines.append("POST-RELEASE: upstream added this license file after the released "
                     "commit; it was not part of the released package or its source tree.")
    else:
        lines.append("The license file is present at the released commit.")
    return "\n".join(lines) + "\n"


def npm_collect(source, output):
    ui = safe_path(source, UI)
    lock_path = safe_path(ui, "package-lock.json")
    lock = read_json(lock_path)
    if lock.get("lockfileVersion") != 3 or not isinstance(lock.get("packages"), dict):
        raise ValueError("Expected npm package-lock.json v3 with packages")
    packages = lock["packages"]
    if "" not in packages:
        raise ValueError("Missing lockfile root package")
    root = read_json(safe_path(ui, "package.json"))
    fields = ("dependencies", "optionalDependencies", "peerDependencies", "peerDependenciesMeta")
    for field in fields:
        if root.get(field, {}) != packages[""].get(field, {}):
            raise ValueError(f"Root metadata/lockfile mismatch: {field}")
    installed = {}
    skipped = []
    for key, entry in sorted(packages.items()):
        if not key:
            continue
        package_key(key)
        if entry.get("link"):
            raise ValueError(f"npm links/workspaces are not supported: {key}")
        if entry.get("dev") is True:
            continue
        path = safe_path(ui, key)
        if not path.exists():
            if entry.get("optional") is True:
                skipped.append(key)
                continue
            raise ValueError(f"Missing production npm dependency: {key}")
        metadata_path = safe_path(path, "package.json")
        metadata = read_json(metadata_path)
        expected_name = entry.get("name") or key.rsplit("node_modules/", 1)[1]
        if (metadata.get("version") != entry.get("version")
                or metadata.get("name") != expected_name
                or not isinstance(metadata.get("version"), str)):
            raise ValueError(f"Installed npm metadata/lockfile mismatch: {key}")
        for field in fields:
            if metadata.get(field, {}) != entry.get(field, {}):
                raise ValueError(f"Installed npm dependency metadata mismatch: {key}: {field}")
        declaration = spdx(metadata.get("license"))
        if entry.get("license") is not None and entry["license"] != declaration:
            raise ValueError(f"Installed npm license/lockfile mismatch: {key}")
        installed[key] = (metadata, path, declaration)

    # Validate Node's ancestor lookup, not just the lockfile's dev/optional flags.
    # A missing optional installation is allowed, but its installed closure isn't.
    def resolve(owner, name):
        dependency_name(name)
        current = PurePosixPath(owner)
        candidates = []
        while str(current) != ".":
            if current.name != "node_modules":
                candidates.append((current / "node_modules" / name).as_posix())
            current = current.parent
        candidates.append("node_modules/" + name)
        return next((c for c in candidates if c in installed), None)

    reachable = set()
    pending = [("", root)]
    while pending:
        owner, metadata = pending.pop()
        optional = metadata.get("optionalDependencies", {})
        required = {**metadata.get("dependencies", {}), **optional}
        required.update(metadata.get("peerDependencies", {}))
        for name in sorted(required):
            target = resolve(owner, name)
            may_omit = (name in optional or metadata.get("peerDependenciesMeta", {})
                        .get(name, {}).get("optional") is True)
            if target is None:
                if may_omit:
                    continue
                raise ValueError(f"Unresolved production npm dependency: {owner}: {name}")
            if target not in reachable:
                reachable.add(target)
                pending.append((target, installed[target][0]))
    if reachable != set(installed):
        raise ValueError("Production npm lock contains unreachable installations: "
                         + ", ".join(sorted(set(installed) - reachable)))

    vendored = vendored_licenses()
    copy_bytes(lock_path, output / "npm/package-lock.json")
    copy_bytes(safe_path(ui, "package.json"), output / "npm/package.json")
    records = []
    for key, (metadata, path, declaration) in sorted(installed.items()):
        destination = output / "npm" / key
        copy_bytes(path / "package.json", destination / "package.json")
        files = legal_files(path)
        record = {
            "path": key, "name": metadata["name"], "version": metadata["version"],
            "license": declaration, "metadata": f"npm/{key}/package.json",
        }
        if not has_license_text(files):
            match = vendored.get((metadata["name"], metadata["version"]))
            if match is None:
                raise ValueError(f"No license text found in npm package: {path}")
            entry, original = match
            if entry["license"] != declaration:
                raise ValueError(f"Vendored license declaration mismatch: {key}")
            name = "LICENSE.vendored"
            if any(n.casefold() in (name.casefold(), VENDORED_NOTICE.casefold())
                   for n, _ in files):
                raise ValueError(f"Vendored license name collision: {key}")
            files = sorted(files + [(name, original)])
            record["vendored"] = {
                "repository": entry["repository"], "provenance": entry["provenance"],
                "release_commit": entry["release_commit"],
                "license_commit": entry["license_commit"],
                "source_path": entry["source_path"], "sha256": entry["sha256"],
                "file": f"npm/{key}/{name}", "notice": f"npm/{key}/{VENDORED_NOTICE}",
            }
            destination.mkdir(parents=True, exist_ok=True)
            (destination / VENDORED_NOTICE).write_bytes(vendored_notice(
                metadata["name"], metadata["version"], declaration, entry).encode())
        for name, original in files:
            relative(name)
            copy_bytes(original, destination / name)
        record["files"] = [f"npm/{key}/{name}" for name, _ in files]
        if "vendored" in record:
            record["files"] = sorted(record["files"] + [record["vendored"]["notice"]])
        records.append(record)
    return {"packages": records, "absent_optional": skipped}


def inventory(root):
    files = {}
    folded = set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"Symlink in collected licenses: {path}")
            key = path.relative_to(root).as_posix()
            relative(key)
            if key.casefold() in folded:
                raise ValueError(f"Case-colliding archive path: {key}")
            folded.add(key.casefold())
        for name in names:
            path = Path(directory) / name
            key = path.relative_to(root).as_posix()
            if key != "manifest.json":
                files[key] = sha256(read_file(path))
    return dict(sorted(files.items()))


def verify(output):
    output = Path(output)
    manifest = read_json(safe_path(output, "manifest.json"))
    if manifest.get("schema") != 1 or manifest.get("files") != inventory(output):
        raise ValueError("License inventory mismatch (missing, added or modified files)")
    return manifest


def collect(source, output):
    source = Path(source).resolve(strict=True)
    supplied_output = Path(output).absolute()
    # Reject symlink ancestors, even if they resolve back inside the intended tree.
    for ancestor in (supplied_output, *supplied_output.parents):
        if ancestor.is_symlink():
            raise ValueError(f"Symlink output path: {ancestor}")
    output = supplied_output.resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("License output must be outside and separate from the checkout")
    if output.exists():
        raise ValueError("License output must not already exist")
    env = os.environ.copy()
    if env.get("CGO_ENABLED") not in (None, "0"):
        raise ValueError("Native license closure requires CGO_ENABLED=0")
    env["CGO_ENABLED"] = "0"
    # go list, used internally by go-licenses, must not repair the source locks.
    env["GOFLAGS"] = (env.get("GOFLAGS", "") + " -mod=readonly").strip()
    revision = run(["git", "rev-parse", "HEAD"], source).decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Expected immutable upstream HEAD")
    original_license = run(["git", "show", "HEAD:LICENSE"], source)
    if not original_license.strip():
        raise ValueError("Empty upstream license")
    identity = json.loads(run(["go", "mod", "download", "-json",
                               f"{GO_MODULE}@{GO_VERSION}"], source, env))
    if (identity.get("Path") != GO_MODULE or identity.get("Version") != GO_VERSION
            or identity.get("Origin", {}).get("Hash") != GO_COMMIT
            or identity.get("Error")
            or not all(re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", identity.get(k, ""))
                       for k in ("Sum", "GoModSum"))):
        raise ValueError("Cannot verify pinned go-licenses tool identity")
    output.mkdir(parents=True)
    # manifest.json is written last: partial output is never a successful bundle.
    npm = npm_collect(source, output)
    (output / "LICENSE-LocalAI").write_bytes(original_license)
    vendored = vendored_go_licenses()
    allowed_empty = vendored_go_empty_files()
    build = go_build(source, env) if vendored or allowed_empty else {}
    ignores = go_ignores(build, vendored)
    go_empty_files(build, allowed_empty)
    ignore_args = [a for p in ignores for a in ("--ignore", p)]
    args = ["go", "run", f"{GO_MODULE}@{GO_VERSION}", "save", GO_PACKAGE,
            *ignore_args, "--save_path", str(output / "go")]
    run(args, source, env)
    # Check go-licenses' own output before vendored files are added beside it.
    saved = inventory(output)
    if not any(key.startswith("go/") for key in saved):
        raise ValueError("go-licenses produced no legal materials")
    # Reciprocal-license source copies may contain listed, genuinely empty files only.
    empty = sorted(key for key in saved
                   if key.startswith("go/") and not read_file(output / key).strip())
    unlisted = [key for key in empty if key not in allowed_empty
                or read_file(output / key) != b""]
    if unlisted:
        raise ValueError("go-licenses produced empty files: " + ", ".join(unlisted))
    stale = sorted(set(allowed_empty) - set(empty))
    if stale:
        raise ValueError("Allowed empty Go files missing or not empty: " + ", ".join(stale))
    go_vendored = []
    for module, (entry, original) in sorted(vendored.items()):
        destination = output / "go" / module
        if destination.exists():
            raise ValueError(f"go-licenses also saved vendored Go module: {module}")
        target = PurePosixPath(entry["file"]).name if (
            entry["provenance"] == "readme-statement") else entry["source_path"]
        copy_bytes(original, destination / target)
        (destination / VENDORED_NOTICE).write_bytes(vendored_go_notice(entry).encode())
        go_vendored.append({
            "module": module, "version": entry["version"], "packages": entry["packages"],
            "license": entry["license"], "provenance": entry["provenance"],
            "sha256": entry["sha256"], "file": f"go/{module}/{target}",
            "notice": f"go/{module}/{VENDORED_NOTICE}",
            **({k: entry[k] for k in ("repository", "commit", "source_path", "source_sha256",
                                      "statement", "statement_line")}
               if entry["provenance"] == "readme-statement" else {}),
        })
    files = inventory(output)
    manifest = {
        "schema": 1, "source": {"revision": revision, "license": "HEAD:LICENSE"},
        "go": {"module": GO_MODULE, "version": GO_VERSION, "commit": GO_COMMIT,
               "sum": identity["Sum"], "go_mod_sum": identity["GoModSum"],
               "package": "./cmd/local-ai", "cgo_enabled": "0",
               "command": ["go", "run", f"{GO_MODULE}@{GO_VERSION}", "save",
                           GO_PACKAGE, *ignore_args, "--save_path", "OUTPUT/go"],
               "vendored": go_vendored,
               "allowed_empty_files": [allowed_empty[k] for k in empty]},
        "npm": npm, "files": files,
    }
    write_json(output / "manifest.json", manifest)
    verify(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_checkout", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        collect(args.upstream_checkout, args.output_dir)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"License collection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
