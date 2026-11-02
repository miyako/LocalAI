[![license](https://img.shields.io/github/license/miyako/LocalAI)](LICENSE)
[![native server build](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml/badge.svg)](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml)

# LocalAI

Native [LocalAI](https://github.com/mudler/LocalAI) server source builds and a
separate **4D 20+ component**. [4D usage / GitHub Pages](https://miyako.github.io/LocalAI/).
The component version in `package.json` is **not** the upstream server version.
The existing [component publishing workflow](.github/workflows/publish.yml) is preserved.

## Native server CLI

[Build workflow and downloadable CI artifacts](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml)
| [Published releases](https://github.com/miyako/LocalAI/releases)
| [Upstream source](https://github.com/mudler/LocalAI)

**Server-CLI-only** archives contain a source-built `bin/local-ai` and embedded
web UI, **not inference backends, model weights, Python environments or GPU
drivers**. A healthy empty server is not an inference-ready installation.
No upstream prebuilt server binary is downloaded.

### Version and platform policy

With an empty `upstream_ref`, **latest** means the tag returned by upstream's
GitHub **latest published, non-prerelease release** API, not `master`, a moving
backend image tag, or this repository's latest component release. One resolution
job converts that tag to a full commit SHA before the entire matrix runs.
Manual builds accept an exact `vX.Y.Z` tag (optional suffix) or full lowercase
40-character SHA to rebuild a specific source revision.

The source baseline verified on **2026-11-02** is **v4.12.1**,
[`ec9274027eadd552d56f2c6c1fe86cd9216a991a`](https://github.com/mudler/LocalAI/tree/ec9274027eadd552d56f2c6c1fe86cd9216a991a).
Future default runs resolve latest again; all matrix jobs still use one SHA.

| Target | Native GitHub runner | Server runtime / status |
|---|---|---|
| `darwin-arm64` | `macos-15` (Apple Silicon) | macOS 15+ target; system libraries only, ad-hoc signed, **not notarized** |
| `linux-amd64` | `ubuntu-24.04` | CGO-disabled static server; Ubuntu 24.04 CI baseline |
| `linux-arm64` | `ubuntu-24.04-arm` | Same, ARM64 host, no emulation |

This follows upstream's v4.12.1 server release scope. **Intel macOS and native
Windows are not built or supported here**; upstream excludes Darwin amd64 and
Windows from its server release configuration. Older component platform badges
did not establish current native server support. WSL2 users may use the matching
Linux archive *inside WSL2*; it is not a Windows `.exe`, and the Windows 4D
`SystemWorker` launcher cannot execute it directly.

The workflow asserts the runner's actual architecture and audits the built
binary: macOS must depend only on system libraries, Linux must have no ELF
interpreter or required shared libraries. Backend libraries are a separate
concern. Each **extracted archive** must pass CLI version/help, `/healthz`,
`/readyz`, empty `/v1/models`, and embedded UI smoke tests before upload.
The local end-to-end source build, archive extraction and live HTTP checks passed
on macOS 26.7 arm64 with Go 1.26.0, Node 26.8.1/npm 11.19.0 and protoc 31.1.
Linux jobs and GitHub-hosted runners (including macOS 15 with Node 22) still
require their first CI execution. No inference workload or 4D runtime was
exercised by these checks.

### Build, download and install

Use **Actions > Build native LocalAI server > Run workflow**. The default
`publish=false` only uploads CI artifacts. To publish, explicitly dispatch on
`main` with `publish=true`; publishing waits for all three native smoke tests.
There is no scheduled publication. Server releases use unique
`server-<version>-<sha12>-<run-id>-<attempt>` tags and `--latest=false`, leaving
the latest 4D component release untouched. Re-runs never overwrite server assets.

Each CI artifact wraps one archive and its `.sha256` file. Published server
releases instead have three archives and a combined `SHA256SUMS`. Example name:

```text
local-ai-v4.12.1-ec9274027ead-darwin-arm64-server-cli-only.tar.gz
```

Archives contain `bin/local-ai`, upstream `LICENSE-LocalAI`, `PACKAGE.txt`,
`provenance.json` (upstream ref/SHA, builder SHA, tool versions, lock hashes,
binary hash, target and signing status), `build-info.txt`, a runtime dependency
audit and the source's Go/npm lock files. Dependencies use upstream `go.sum`,
`npm ci`, and upstream-pinned protobuf generators. Tool versions are recorded;
source-pinned rebuilds are supported, **byte-for-byte reproducibility across
different toolchains/runners is not claimed**. Check upstream and dependency
licenses before redistribution; inference backend/model licenses are separate.

For example, after selecting a **server** release tag from Releases:

```sh
# Replace with a real server-* release tag and the version/SHA recorded there.
RELEASE_TAG=server-v4.12.1-ec9274027ead-RUN_ID-ATTEMPT
ASSET=local-ai-v4.12.1-ec9274027ead-darwin-arm64-server-cli-only.tar.gz
gh release download "$RELEASE_TAG" --repo miyako/LocalAI \
  --pattern "$ASSET" --pattern SHA256SUMS
# Check only the archive you downloaded. Use sha256sum on Linux.
grep "  $ASSET\$" SHA256SUMS | shasum -a 256 --check
mkdir -p localai-server
tar -xzf "$ASSET" -C localai-server
./localai-server/bin/local-ai --help
```

No server assets have been published merely by adding this workflow. CI artifacts
require an authenticated Actions download and expire after 30 days. On macOS,
Gatekeeper may block downloaded, non-notarized executables: inspect the source
and checksum, then follow your organization's approval policy or build locally.
There is no automatic quarantine bypass or Developer ID signing in this workflow.

### Run the server and use the API

Bind explicitly to loopback; the upstream default `:8080` exposes all interfaces.
Run in a writable directory; server configuration, uploads, data and generated
content require persistent storage in addition to the model/backend directories.

```sh
mkdir -p "$HOME/.localai-native"/{models,backends}
export LOCALAI_MODELS_PATH="$HOME/.localai-native/models"
export LOCALAI_BACKENDS_PATH="$HOME/.localai-native/backends"
# From the extracted localai-server directory:
SERVER="$PWD/bin/local-ai"
cd "$HOME/.localai-native"
"$SERVER" run --address 127.0.0.1:8080 \
  --models-path "$LOCALAI_MODELS_PATH" --backends-path "$LOCALAI_BACKENDS_PATH"
```

In another terminal:

```sh
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/readyz
curl --fail http://127.0.0.1:8080/v1/models
# Web UI: http://127.0.0.1:8080/
```

For inference, first select a compatible backend and model from the current
galleries. The commands below illustrate the CLI; availability, identifiers,
downloads and runtime requirements are controlled by upstream, not these archives:

```sh
./bin/local-ai backends list
./bin/local-ai backends install --help
./bin/local-ai models list
./bin/local-ai models install --help
# Set LOCALAI_MODELS_PATH / LOCALAI_BACKENDS_PATH in this terminal as above.
# Then install compatible entries using the exact gallery IDs shown by list.
```

CPU/Metal/CUDA/Vulkan backends have independent platform/CPU/GPU requirements.
Some backends need Python/uv, system shared libraries, GPU drivers or an external
gRPC worker; installing the server does not supply these. macOS ARM64 backend
availability is narrower than Linux's. Gallery entries and backend image tags
can change independently of the pinned server. Consult
[upstream backend documentation](https://localai.io/backends/) and pin/verify
backend artifacts separately for repeatable or offline inference.

After an embedding model is installed and loaded, use its **actual API model ID**
from `/v1/models`:

```sh
curl --fail http://127.0.0.1:8080/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"YOUR_INSTALLED_EMBEDDING_MODEL_ID","input":"The quick brown fox jumps over the lazy dog."}'
```

Do not treat every OpenAI endpoint as available for every model/backend.
Before exposing this server beyond loopback, configure upstream authentication,
network access controls and storage policy.

### Build locally from the same source

Requirements: native supported host, Git, GitHub CLI, Python 3.11+, Go (automatic
toolchain selection enabled; v4.12.1 requires Go 1.26.0), Node.js 22.12+ / npm,
Make, curl and unzip. macOS also needs Xcode Command Line Tools (`codesign`,
`otool`); Linux needs binutils (`readelf`). No CMake, llama static library,
Windows vcpkg or obsolete `llamacpp,tflite` Go tags are required for this server.
The upstream Makefile obtains protoc 31.1 and pinned Go protobuf plugins.
Network access and several GB of dependency/build cache space are required.

From a checkout of this repository:

```sh
python3 scripts/native/native.py resolve --ref v4.12.1 --output source.json
git clone --filter=blob:none --no-checkout https://github.com/mudler/LocalAI.git upstream
SHA=$(python3 -c 'import json; print(json.load(open("source.json"))["sha"])')
git -C upstream checkout --detach "$SHA"
bash scripts/native/build.sh upstream source.json dist
mkdir -p extracted
tar -xzf dist/*.tar.gz -C extracted
python3 scripts/native/native.py smoke extracted/bin/local-ai "$SHA" v4.12.1
```

Generated files remain in the upstream checkout; do not edit tracked upstream
sources before running the build helper. Unsupported manual revisions may fail
if upstream changes its build/CLI interfaces: the workflow deliberately fails
rather than patching upstream silently or publishing untested packages.

## 4D component

See [Pages usage](https://miyako.github.io/LocalAI/) and
[class documentation](LocalAI/Documentation/Classes/_LocalAI.md).
The 4D publishing workflow builds the component; the server workflow does **not**
embed or update its executable resources. Native server archives are installed
separately. Existing Windows/Intel component resources remain legacy,
best-effort launch paths; they are not new v4.12.1 builds or part of the native
server matrix above. Do not copy a Linux binary into Windows component resources.
Their exact upstream server versions are not established by this update; neither
the component version nor an executable filename identifies the server version.

For the source-built server through the macOS arm64 launcher, manually replace
`LocalAI/Resources/bin/macOS/local-ai` with the validated archive's `bin/local-ai`
before packaging the component. A bundled resource takes precedence over
`PATH`. Check that `file LocalAI/Resources/bin/macOS/local-ai` reports ARM64 and
its `--help` output contains the version/full SHA from the archive's provenance.
Modern-only options must not be passed to an unchanged legacy executable.
The [class guide](LocalAI/Documentation/Classes/_LocalAI.md) distinguishes generic
legacy-compatible usage from replacement-specific options. Empty backend/model
collections select the component's downloadable defaults, not offline operation;
installation callbacks do not establish server readiness.

## Validation helpers

```sh
python3 -m unittest discover -s scripts/native -p 'test_*.py' -v
shellcheck scripts/native/build.sh
actionlint .github/workflows/build-server.yml
```
