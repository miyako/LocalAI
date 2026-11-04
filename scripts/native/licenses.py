#!/usr/bin/env python3
"""Collect native CLI/UI legal materials without modifying the checkout.

Usage: python3 licenses.py UPSTREAM_CHECKOUT OUTPUT_DIR

OUTPUT_DIR must not exist and must be outside the checkout. Ship the entire
directory, including manifest.json, LICENSE-LocalAI, go/ and npm/. The manifest
inventories every file except itself. verify() checks that inventory exactly.

The npm SPDX vocabulary below is deliberately conservative, not a legal policy:
unsupported declarations fail rather than being inferred from package contents.
New identifiers require explicit review. License text is never synthesized.
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
    if not any(LICENSE.match(Path(name).name)
               or any(p.lower() in ("licenses", "licences")
                      for p in PurePosixPath(name).parts[:-1]) for name, _ in result):
        raise ValueError(f"No license text found in npm package: {package}")
    return sorted(result)


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

    copy_bytes(lock_path, output / "npm/package-lock.json")
    copy_bytes(safe_path(ui, "package.json"), output / "npm/package.json")
    records = []
    for key, (metadata, path, declaration) in sorted(installed.items()):
        destination = output / "npm" / key
        copy_bytes(path / "package.json", destination / "package.json")
        files = legal_files(path)
        for name, original in files:
            relative(name)
            copy_bytes(original, destination / name)
        records.append({
            "path": key, "name": metadata["name"], "version": metadata["version"],
            "license": declaration, "metadata": f"npm/{key}/package.json",
            "files": [f"npm/{key}/{name}" for name, _ in files],
        })
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
    args = ["go", "run", f"{GO_MODULE}@{GO_VERSION}", "save",
            "./cmd/local-ai", "--save_path", str(output / "go")]
    run(args, source, env)
    files = inventory(output)
    if not any(key.startswith("go/") for key in files):
        raise ValueError("go-licenses produced no legal materials")
    if any(not read_file(output / key).strip() for key in files if key.startswith("go/")):
        raise ValueError("go-licenses produced empty files")
    manifest = {
        "schema": 1, "source": {"revision": revision, "license": "HEAD:LICENSE"},
        "go": {"module": GO_MODULE, "version": GO_VERSION, "commit": GO_COMMIT,
               "sum": identity["Sum"], "go_mod_sum": identity["GoModSum"],
               "package": "./cmd/local-ai", "cgo_enabled": "0",
               "command": ["go", "run", f"{GO_MODULE}@{GO_VERSION}", "save",
                           "./cmd/local-ai", "--save_path", "OUTPUT/go"]},
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
