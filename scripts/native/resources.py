#!/usr/bin/env python3
"""Validate the complete native matrix and stage transient component Resources."""

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import tarfile
import tempfile

from native import LOCK_PATHS, UPSTREAM, digest
import licenses as dependency_licenses


TARGETS = {"darwin-arm64", "linux-amd64", "linux-arm64"}
RESOURCE = "LocalAI/Resources"
MAC_BINARY = "bin/macOS/local-ai"
LEGACY = ("bin/macOS/local-ai-x86_64", "bin/Windows/local-ai.exe")
SMOKE_CHECKS = ["version-help", "run-models-backends-help", "healthz", "readyz",
                "empty-models", "embedded-ui"]


def portable(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ":" in name
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("Unsafe portable path: " + name)
    return path


def validate_source(source):
    import re
    if (source.get("repository") != UPSTREAM
            or not re.fullmatch(r"[a-f0-9]{40}", source.get("sha", ""))
            or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?|sha-[a-f0-9]{12}",
                                source.get("version", ""))
            or set(source.get("locks", {})) != set(LOCK_PATHS)
            or any(not re.fullmatch(r"[a-f0-9]{64}", value)
                   for value in source["locks"].values())):
        raise ValueError("Invalid source snapshot/lock")


def unpack(archive, destination):
    """Only materialize regular files/directories with bounded portable names."""
    seen = set()
    total = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = member.name.rstrip("/") if member.isdir() else member.name
            portable(name)
            if name in seen or len(seen) >= 20000:
                raise ValueError("Duplicate or excessive archive members")
            seen.add(name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("Archive links/special files are forbidden: " + name)
            total += member.size
            if member.size < 0 or member.size > 512 * 1024 * 1024 or total > 1024 * 1024 * 1024:
                raise ValueError("Archive exceeds extraction bounds")
            path = destination / name
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as content, path.open("xb") as out:
                    shutil.copyfileobj(content, out)
                path.chmod(0o755 if name == "bin/local-ai" else 0o644)


def validate_package(root, target, source, builder):
    info = json.loads((root / "provenance.json").read_text())
    if (info.get("format") != 2 or info.get("target") != target
            or info.get("builder_sha") != builder or info.get("builder_dirty") is not False
            or not info.get("workflow_run")
            or any(info.get(key) != value for key, value in source.items())
            or info.get("smoke") != {"passed": True, "checks": SMOKE_CHECKS}):
        raise ValueError("Mixed, untested or incomplete package provenance: " + target)
    files = {path.relative_to(root).as_posix(): digest(path)
             for path in root.rglob("*") if path.is_file()
             and path != root / "provenance.json"}
    if info.get("files") != files:
        raise ValueError("Package file checksum inventory mismatch: " + target)
    required = {"bin/local-ai", "LICENSE-LocalAI", "PACKAGE.txt", "build-info.txt",
                "runtime-dependencies.txt", "licenses/manifest.json",
                "source-locks/go.mod", "source-locks/go.sum", "source-locks/package-lock.json"}
    if not required <= files.keys() or any((root / name).stat().st_size == 0 for name in required):
        raise ValueError("Missing required runtime/license/source material: " + target)
    if not any(name.startswith("licenses/go/") for name in files) or not any(
            name.startswith("licenses/npm/") for name in files):
        raise ValueError("Missing dependency license closure")
    dependency_licenses.verify(root / "licenses")
    if digest(root / "LICENSE-LocalAI") != digest(root / "licenses/LICENSE-LocalAI"):
        raise ValueError("Upstream license inventory mismatch")
    for path, checksum in source["locks"].items():
        if digest(root / "source-locks" / Path(path).name) != checksum:
            raise ValueError("Shipped source lock hash mismatch: " + path)
    binary = root / "bin/local-ai"
    if digest(binary) != info.get("binary_sha256"):
        raise ValueError("Binary checksum mismatch")
    with binary.open("rb") as stream:
        header = stream.read(64)
    build = (root / "build-info.txt").read_text()
    go_os, arch = target.split("-")
    if any(setting not in build for setting in
           ("CGO_ENABLED=0", f"GOOS={go_os}", f"GOARCH={arch}")):
        raise ValueError("Wrong binary build settings")
    runtime = (root / "runtime-dependencies.txt").read_text()
    if target == "darwin-arm64":
        if len(header) < 8 or struct.unpack("<II", header[:8]) != (0xfeedfacf, 0x100000c):
            raise ValueError("Expected arm64 Mach-O executable")
        libraries = [line.strip().split(" (")[0] for line in runtime.splitlines()[1:]]
        if not libraries or any(not lib.startswith(("/usr/lib/", "/System/Library/"))
                                for lib in libraries):
            raise ValueError("Unbundled macOS runtime dependency")
        if info.get("macos_signing") != "ad-hoc, not notarized":
            raise ValueError("Unexpected signing policy")
    else:
        machine = 62 if target == "linux-amd64" else 183
        if (len(header) < 20 or header[:6] != b"\x7fELF\x02\x01"
                or struct.unpack("<H", header[18:20])[0] != machine):
            raise ValueError("Expected native 64-bit ELF executable")
        if "(NEEDED)" in runtime or "INTERP" in runtime:
            raise ValueError("Unbundled Linux runtime dependency")
    return info


def prepare(artifacts, source, builder, output=None):
    validate_source(source)
    if output is not None and output.exists():
        raise ValueError("Staging output must not already exist")
    archives = sorted(artifacts.rglob("*.tar.gz"))
    expected_names = {
        f"local-ai-{source['version']}-{source['sha'][:12]}-{target}-server-cli-only.tar.gz": target
        for target in TARGETS}
    if len(archives) != len(TARGETS) or {a.name for a in archives} != expected_names.keys():
        raise ValueError("Require exactly one archive for every supported target")
    with tempfile.TemporaryDirectory(prefix="localai-resources-") as temp:
        staging = Path(temp)
        validated = {}
        for archive in archives:
            checksum = archive.with_name(archive.name.removesuffix(".tar.gz") + ".sha256")
            expected = f"{digest(archive)}  {archive.name}\n"
            if checksum.read_text() != expected:
                raise ValueError("Archive checksum mismatch: " + archive.name)
            target = expected_names[archive.name]
            root = staging / target
            root.mkdir()
            unpack(archive, root)
            validated[target] = validate_package(root, target, source, builder)
        if len({info["workflow_run"] for info in validated.values()}) != 1:
            raise ValueError("Mixed native workflow runs")
        if output is None:
            return validated
        # All files are transient packaging inputs, never Git commit candidates.
        resources = staging / RESOURCE
        (resources / "bin/macOS").mkdir(parents=True)
        shutil.copy2(staging / "darwin-arm64/bin/local-ai", resources / MAC_BINARY)
        for target in sorted(TARGETS):
            destination = resources / "native" / target
            shutil.copytree(staging / target, destination,
                            ignore=shutil.ignore_patterns("bin"))
        (resources / "native/source.json").write_text(json.dumps(source, indent=2) + "\n")
        shutil.copytree(resources, output / RESOURCE)
    return validated


def install(stage, repo):
    """Only overwrite the arm64 resource and owned native metadata directory."""
    source = stage / RESOURCE
    destination = repo / RESOURCE
    if not source.is_dir() or not (source / MAC_BINARY).is_file():
        raise ValueError("Missing validated staging tree")
    if source.is_symlink() or any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Symlinks are forbidden in transient Resources")
    if (destination / "native").is_symlink():
        raise ValueError("Native Resources destination must not be a symlink")
    if (destination / "native").exists():
        shutil.rmtree(destination / "native")
    shutil.copytree(source / "native", destination / "native")
    shutil.copy2(source / MAC_BINARY, destination / MAC_BINARY)
    (destination / MAC_BINARY).chmod(0o755)
    files = {path.relative_to(destination).as_posix(): digest(path)
             for path in sorted(destination.rglob("*"))
             if path.is_file() and (path.is_relative_to(destination / "native")
                                   or path.relative_to(destination).as_posix() in (MAC_BINARY, *LEGACY))}
    for name in (MAC_BINARY, *LEGACY):
        if name not in files:
            raise ValueError("Required wrapper resource is missing: " + name)
    inventory = destination / "native/inventory.json"
    files.pop("native/inventory.json", None)
    inventory.write_text(json.dumps({"format": 1, "files": files}, indent=2) + "\n")
    verify(repo)


def verify(repo, allow_legacy=False, resource_dir=None):
    resources = resource_dir if resource_dir is not None else repo / RESOURCE
    if (resources / "native").is_symlink() or any(
            path.is_symlink() for path in (resources / "native").rglob("*")):
        raise ValueError("Symlinks are forbidden in native Resources")
    for name in (MAC_BINARY, *LEGACY):
        path = resources / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Missing/invalid wrapper resource: " + name)
    inventory = resources / "native/inventory.json"
    if not inventory.exists():
        if not allow_legacy or (resources / "native").exists():
            raise ValueError("Native resource provenance is missing")
        print("Legacy resource set: upstream versions unknown; no native-update provenance.")
        return
    data = json.loads(inventory.read_text())
    actual = {path.relative_to(resources).as_posix(): digest(path)
              for path in resources.rglob("*")
              if path.is_file() and path != inventory
              and (path.is_relative_to(resources / "native")
                   or path.relative_to(resources).as_posix() in (MAC_BINARY, *LEGACY))}
    if data.get("format") != 1 or data.get("files") != actual:
        raise ValueError("Checked-in resource inventory mismatch")
    source = json.loads((resources / "native/source.json").read_text())
    validate_source(source)
    identities = set()
    for target in TARGETS:
        root = resources / "native" / target
        info = json.loads((root / "provenance.json").read_text())
        if (info.get("target") != target or info.get("smoke", {}).get("passed") is not True
                or any(info.get(key) != value for key, value in source.items())):
            raise ValueError("Incomplete checked-in target provenance")
        shipped = {path.relative_to(root).as_posix(): digest(path)
                   for path in root.rglob("*")
                   if path.is_file() and path != root / "provenance.json"}
        expected = {name: checksum for name, checksum in info["files"].items()
                    if name != "bin/local-ai"}
        if shipped != expected:
            raise ValueError("Packaged native metadata/license hash mismatch")
        dependency_licenses.verify(root / "licenses")
        identities.add((info["builder_sha"], info["workflow_run"]))
    if len(identities) != 1:
        raise ValueError("Mixed packaged native build identities")
    release_lock = resources / "native/component-lock.json"
    if release_lock.exists():
        lock = json.loads(release_lock.read_text())
        if (lock.get("source") != source
                or lock.get("release", {}).get("builder_sha") != next(iter(identities))[0]):
            raise ValueError("Packaged native release lock mismatch")
    mac = json.loads((resources / "native/darwin-arm64/provenance.json").read_text())
    if digest(resources / MAC_BINARY) != mac["binary_sha256"]:
        raise ValueError("Resource executable no longer matches pre-sign build provenance")
    for name in actual:
        portable(name)
    print("Verified native Resources (pre-component-signing bytes).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    stage = actions.add_parser("stage")
    stage.add_argument("--artifacts", type=Path, required=True)
    stage.add_argument("--source", type=Path, required=True)
    stage.add_argument("--builder", required=True)
    stage.add_argument("--output", type=Path, required=True)
    validate = actions.add_parser("validate")
    validate.add_argument("--artifacts", type=Path, required=True)
    validate.add_argument("--source", type=Path, required=True)
    validate.add_argument("--builder", required=True)
    copy = actions.add_parser("install")
    copy.add_argument("--stage", type=Path, required=True)
    copy.add_argument("--repo", type=Path, default=Path("."))
    check = actions.add_parser("verify")
    check.add_argument("--repo", type=Path, default=Path("."))
    check.add_argument("--allow-legacy", action="store_true")
    check.add_argument("--resources", type=Path)
    args = parser.parse_args()
    if args.action in ("stage", "validate"):
        prepare(args.artifacts, json.loads(args.source.read_text()), args.builder,
                args.output if args.action == "stage" else None)
    elif args.action == "install":
        install(args.stage, args.repo)
    else:
        verify(args.repo, args.allow_legacy, args.resources)


if __name__ == "__main__":
    main()
