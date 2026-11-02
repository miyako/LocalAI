#!/usr/bin/env python3
"""Adopt an exact native release, or prepare its locked transient component inputs."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse

from native import digest
import resources


REPOSITORY = "miyako/LocalAI"
LOCK = Path(__file__).with_name("component-lock.json")


def api(endpoint):
    return json.loads(subprocess.check_output(
        ["gh", "api", f"repos/{REPOSITORY}/{endpoint}"], text=True, timeout=120))


def download(asset, path):
    with path.open("xb") as out:
        subprocess.run(["gh", "api", f"repos/{REPOSITORY}/releases/assets/{asset['id']}",
                        "-H", "Accept: application/octet-stream"],
                       stdout=out, check=True, timeout=600)


def asset_names(source):
    return {
        f"local-ai-{source['version']}-{source['sha'][:12]}-{target}-server-cli-only.tar.gz"
        for target in resources.TARGETS} | {"SHA256SUMS"}


def release_info(tag, source, lookup=api):
    if not re.fullmatch(r"server-[A-Za-z0-9.+-]+", tag):
        raise ValueError("Select an exact server-* release tag, never latest/component releases")
    release = lookup("releases/tags/" + urllib.parse.quote(tag, safe=""))
    if (release.get("tag_name") != tag or release.get("draft") is not False
            or release.get("prerelease") is not False
            or not isinstance(release.get("id"), int)):
        raise ValueError("Native release must be published, stable and exactly identified")
    builder = lookup("commits/" + urllib.parse.quote(tag, safe=""))["sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", builder):
        raise ValueError("Release tag does not resolve to an immutable builder SHA")
    assets = release.get("assets", [])
    if (len(assets) != 4 or {asset["name"] for asset in assets} != asset_names(source)
            or len({asset["id"] for asset in assets}) != 4):
        raise ValueError("Native release must contain exactly the complete three-target set and SHA256SUMS")
    for asset in assets:
        resources.portable(asset["name"])
        if (asset.get("state") != "uploaded" or not isinstance(asset.get("id"), int)
                or not isinstance(asset.get("size"), int)
                or not 0 < asset["size"] <= 512 * 1024 * 1024):
            raise ValueError("Incomplete/oversized release asset")
    return {"id": release["id"], "tag": tag, "builder_sha": builder}, {
        asset["name"]: {"id": asset["id"], "size": asset["size"]} for asset in assets}


def checksums(path, expected):
    result = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([A-Za-z0-9.+-]+\.tar\.gz)", line)
        if not match or match[2] in result:
            raise ValueError("Malformed/duplicate native SHA256SUMS entry")
        result[match[2]] = match[1]
    if set(result) != expected:
        raise ValueError("Incomplete native SHA256SUMS target set")
    return result


def fetch(tag, source, directory, pinned=None, lookup=api, downloader=download):
    resources.validate_source(source)
    release, assets = release_info(tag, source, lookup)
    if pinned is not None:
        expected_assets = {name: {"id": asset["id"], "size": asset["size"]}
                           for name, asset in pinned["assets"].items()}
        if release != pinned["release"] or assets != expected_assets:
            raise ValueError("Native release/tag/asset identity changed since lock adoption")
    directory.mkdir()
    for name, asset in sorted(assets.items()):
        destination = directory / name
        downloader(asset, destination)
        if destination.stat().st_size != asset["size"]:
            raise ValueError("Release asset size mismatch: " + name)
        checksum = digest(destination)
        if pinned is not None and pinned["assets"][name]["sha256"] != checksum:
            raise ValueError("Locked release asset checksum mismatch: " + name)
        asset["sha256"] = checksum
    expected = checksums(directory / "SHA256SUMS", set(assets) - {"SHA256SUMS"})
    for name, checksum in expected.items():
        if assets[name]["sha256"] != checksum:
            raise ValueError("Release archive does not match SHA256SUMS: " + name)
        (directory / (name.removesuffix(".tar.gz") + ".sha256")).write_text(
            f"{checksum}  {name}\n")
    # Refetch identity after download to reject deletion/reupload or moving tags.
    after_release, after_assets = release_info(tag, source, lookup)
    if after_release != release or after_assets != {
            name: {"id": asset["id"], "size": asset["size"]} for name, asset in assets.items()}:
        raise ValueError("Native release changed while downloading")
    return {"format": 1, "status": "configured", "repository": REPOSITORY,
            "release": release, "source": source, "assets": assets}


def load_lock(path=LOCK):
    lock = json.loads(path.read_text())
    if lock.get("status") == "unconfigured":
        raise ValueError(
            "Native component release lock is unconfigured. First publish a validated "
            "server-* release, run release.py adopt --tag EXACT_TAG, then review/commit "
            "the lock before Publish. No latest/legacy fallback is allowed.")
    if (lock.get("format") != 1 or lock.get("status") != "configured"
            or lock.get("repository") != REPOSITORY):
        raise ValueError("Invalid native component release lock")
    resources.validate_source(lock["source"])
    if set(lock["assets"]) != asset_names(lock["source"]):
        raise ValueError("Incomplete locked native release asset set")
    for asset in lock["assets"].values():
        if not re.fullmatch(r"[a-f0-9]{64}", asset.get("sha256", "")):
            raise ValueError("Invalid locked asset checksum")
    return lock


def adopt(tag, source, output, lookup=api, downloader=download):
    with tempfile.TemporaryDirectory(prefix="localai-adopt-") as temp:
        archives = Path(temp) / "archives"
        lock = fetch(tag, source, archives, lookup=lookup, downloader=downloader)
        resources.prepare(archives, source, lock["release"]["builder_sha"])
        serialized = json.dumps(lock, indent=2, sort_keys=True) + "\n"
        if len(serialized.encode()) >= 100 * 1024 * 1024:
            raise ValueError("Lock exceeds GitHub's file limit")
        output.write_text(serialized)
    return lock


def prepare(lock_path, output, lookup=api, downloader=download):
    lock = load_lock(lock_path)
    if output.exists():
        raise ValueError("Transient output must be new (use a fresh runner temp directory)")
    with tempfile.TemporaryDirectory(prefix="localai-fetch-") as temp:
        archives = Path(temp) / "archives"
        fetch(lock["release"]["tag"], lock["source"], archives, pinned=lock,
              lookup=lookup, downloader=downloader)
        resources.prepare(archives, lock["source"], lock["release"]["builder_sha"], output)
        (output / resources.RESOURCE / "native/component-lock.json").write_bytes(lock_path.read_bytes())
    print("Prepared checksum/source-verified native release; no Git resource files modified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    adoption = actions.add_parser("adopt")
    adoption.add_argument("--tag", required=True)
    adoption.add_argument("--source", type=Path, default=Path(__file__).with_name("source-lock.json"))
    adoption.add_argument("--output", type=Path, default=LOCK)
    preparation = actions.add_parser("prepare")
    preparation.add_argument("--lock", type=Path, default=LOCK)
    preparation.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "adopt":
        adopt(args.tag, json.loads(args.source.read_text()), args.output)
        print(f"Wrote {args.output}. Review and commit only this text lock; no binaries were staged.")
    else:
        prepare(args.lock, args.output)


if __name__ == "__main__":
    main()
