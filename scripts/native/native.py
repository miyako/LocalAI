#!/usr/bin/env python3
"""Resolve, package and exercise the native LocalAI server (stdlib only)."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


UPSTREAM = "mudler/LocalAI"
TARGETS = {("Darwin", "arm64"): "darwin-arm64",
           ("Linux", "x86_64"): "linux-amd64",
           ("Linux", "aarch64"): "linux-arm64"}


def command(*args, cwd=None, env=None):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def api(endpoint):
    return json.loads(command("gh", "api", f"repos/{UPSTREAM}/{endpoint}"))


def resolve(ref, lookup=api):
    if not ref:
        release = lookup("releases/latest")
        if release["draft"] or release["prerelease"]:
            raise ValueError("Latest release must be stable and published")
        ref = release["tag_name"]
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?|[0-9a-f]{40}", ref):
        raise ValueError("Expected an exact vX.Y.Z tag (optional suffix) or full lowercase commit SHA")
    commit = lookup("commits/" + urllib.parse.quote(ref, safe=""))
    sha = commit["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid upstream commit SHA")
    if re.fullmatch(r"[0-9a-f]{40}", ref) and sha != ref:
        raise ValueError("Upstream did not resolve the requested SHA")
    version = ref if ref.startswith("v") else "sha-" + sha[:12]
    return {"repository": UPSTREAM, "ref": ref, "sha": sha, "version": version,
            "commit_date": commit["commit"]["committer"]["date"]}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package(source, metadata, output):
    source, output = source.resolve(), output.resolve()
    info = json.loads(metadata.read_text())
    if command("git", "rev-parse", "HEAD", cwd=source) != info["sha"]:
        raise ValueError("Checkout does not match resolved upstream SHA")
    target = TARGETS.get((platform.system(), platform.machine()))
    if target is None:
        raise ValueError("Unsupported native host; no cross-compilation is advertised")
    binary = source / "local-ai"
    build_info = command("go", "version", "-m", str(binary))
    expected_os, expected_arch = target.split("-")
    for setting in ("CGO_ENABLED=0", f"GOOS={expected_os}", f"GOARCH={expected_arch}"):
        if setting not in build_info:
            raise ValueError("Binary is missing required build setting: " + setting)
    if platform.system() == "Darwin":
        runtime = command("otool", "-L", str(binary))
        libraries = [line.strip().split(" (")[0] for line in runtime.splitlines()[1:]]
        if any(not lib.startswith(("/usr/lib/", "/System/Library/")) for lib in libraries):
            raise ValueError("Unbundled non-system macOS dynamic library: " + runtime)
        command("codesign", "--verify", "--strict", str(binary))
    else:
        runtime = command("readelf", "-l", "-d", str(binary))
        if "(NEEDED)" in runtime or "INTERP" in runtime:
            raise ValueError("Expected a static CGO-disabled Linux server: " + runtime)
    info.update({
        "target": target, "scope": "server-cli-only; no inference backends or model weights",
        "builder_sha": os.environ.get("GITHUB_SHA") or command(
            "git", "rev-parse", "HEAD", cwd=Path(__file__).resolve().parents[2]),
        "builder_dirty": bool(command(
            "git", "status", "--porcelain", "--untracked-files=no",
            cwd=Path(__file__).resolve().parents[2])),
        "workflow_run": os.environ.get("GITHUB_RUN_ID"),
        "tools": {name: command(*args, cwd=source) for name, args in {
            "go": ("go", "version"), "node": ("node", "--version"),
            "npm": ("npm", "--version"), "protoc": ("./protoc", "--version"),
        }.items()},
        "locks": {name: digest(source / name) for name in
                  ("go.mod", "go.sum", "core/http/react-ui/package-lock.json")},
        "binary_sha256": digest(binary),
        "macos_signing": "ad-hoc, not notarized" if expected_os == "darwin" else None,
    })
    name = f"local-ai-{info['version']}-{info['sha'][:12]}-{target}-server-cli-only"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "bin").mkdir()
        shutil.copy2(binary, root / "bin/local-ai")
        (root / "bin/local-ai").chmod(0o755)
        (root / "provenance.json").write_text(json.dumps(info, indent=2) + "\n")
        (root / "build-info.txt").write_text(build_info + "\n")
        (root / "runtime-dependencies.txt").write_text(runtime + "\n")
        shutil.copy2(source / "LICENSE", root / "LICENSE-LocalAI")
        locks = root / "source-locks"
        locks.mkdir()
        for path in ("go.mod", "go.sum", "core/http/react-ui/package-lock.json"):
            shutil.copy2(source / path, locks / Path(path).name)
        (root / "PACKAGE.txt").write_text(
            "LocalAI native server CLI only, built from https://github.com/mudler/LocalAI\n"
            "Embedded web UI included. No model weights, inference backends, Python,\n"
            "GPU drivers or backend shared libraries are bundled. Gallery installation\n"
            "requires network access and backend-specific runtimes. See:\n"
            "https://github.com/miyako/LocalAI#native-server-cli\n"
            "macOS binaries are ad-hoc signed, not Developer ID signed/notarized.\n"
        )
        archive = output / (name + ".tar.gz")
        with archive.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in sorted(root.rglob("*")):
                    entry = tar.gettarinfo(str(path), arcname=str(path.relative_to(root)))
                    entry.uid = entry.gid = entry.mtime = 0
                    entry.uname = entry.gname = ""
                    if path.is_file():
                        with path.open("rb") as content:
                            tar.addfile(entry, content)
                    else:
                        tar.addfile(entry)
    (output / (name + ".sha256")).write_text(f"{digest(archive)}  {archive.name}\n")
    print(archive)


def smoke(binary, sha, version):
    binary = binary.resolve()
    with tempfile.TemporaryDirectory(prefix="localai-smoke-") as temp:
        root = Path(temp)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("LOCALAI_", "PRELOAD_", "HF_", "AWS_"))
               and key in ("PATH", "TMPDIR", "SYSTEMROOT", "LANG")}
        env.update(HOME=temp, XDG_CONFIG_HOME=temp, XDG_DATA_HOME=temp, NO_COLOR="1")
        help_text = command(str(binary), "--help", cwd=root, env=env)
        if sha not in help_text or version not in help_text:
            raise ValueError("CLI help does not contain expected upstream version and SHA")
        for subcommand in ("run", "models", "backends"):
            command(str(binary), subcommand, "--help", cwd=root, env=env)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        args = [str(binary), "run", "--address", f"127.0.0.1:{port}",
                "--galleries", "[]", "--backend-galleries", "[]",
                "--autoload-galleries=false", "--autoload-backend-galleries=false",
                "--disable-agents", "--disable-local-ai-assistant", "--disable-mcp"]
        for flag, folder in {
            "models-path": "models", "backends-path": "backends",
            "backends-system-path": "system-backends", "data-path": "data",
            "localai-config-dir": "configuration", "generated-content-path": "generated",
            "upload-path": "uploads", "download-staging-path": "downloads",
        }.items():
            path = root / folder
            path.mkdir()
            args.extend(["--" + flag, str(path)])
        with (root / "server.log").open("w+") as log:
            process = subprocess.Popen(args, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 120
                base = f"http://127.0.0.1:{port}"
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"Server exited with {process.returncode}")
                    try:
                        with urllib.request.urlopen(base + "/readyz", timeout=2) as response:
                            if response.status == 200:
                                break
                    except (urllib.error.URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Server did not become ready in 120 seconds")
                        time.sleep(0.5)
                for endpoint in ("/healthz", "/readyz", "/v1/models", "/"):
                    with urllib.request.urlopen(base + endpoint, timeout=10) as response:
                        body = response.read()
                        if response.status != 200:
                            raise ValueError("Unexpected status for " + endpoint)
                        if endpoint == "/v1/models" and json.loads(body).get("data") != []:
                            raise ValueError("Expected empty OpenAI model list")
                        if endpoint == "/" and b"<html" not in body.lower():
                            raise ValueError("Embedded UI was not served")
                    print(f"PASS {endpoint}: HTTP 200")
            except BaseException:
                log.flush()
                print((root / "server.log").read_text())
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    print(f"PASS CLI version/help and isolated server: {version} ({sha})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    resolver = sub.add_parser("resolve")
    resolver.add_argument("--ref", default="")
    resolver.add_argument("--output", type=Path, required=True)
    packager = sub.add_parser("package")
    packager.add_argument("source", type=Path)
    packager.add_argument("metadata", type=Path)
    packager.add_argument("output", type=Path)
    tester = sub.add_parser("smoke")
    tester.add_argument("binary", type=Path)
    tester.add_argument("sha")
    tester.add_argument("version")
    args = parser.parse_args()
    if args.action == "resolve":
        info = resolve(args.ref)
        args.output.write_text(json.dumps(info, indent=2) + "\n")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as out:
                for key in ("sha", "version"):
                    out.write(f"{key}={info[key]}\n")
        print(json.dumps(info, indent=2))
    elif args.action == "package":
        package(args.source, args.metadata, args.output)
    else:
        smoke(args.binary, args.sha, args.version)


if __name__ == "__main__":
    main()
