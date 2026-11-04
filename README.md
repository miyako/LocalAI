[![license](https://img.shields.io/github/license/miyako/LocalAI)](LICENSE)
[![native server build](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml/badge.svg)](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml)

# LocalAI

Native [LocalAI](https://github.com/mudler/LocalAI) server source builds and a
separate **4D 20+ component**. [4D usage / GitHub Pages](https://miyako.github.io/LocalAI/).
The component version in `package.json` is **not** the upstream server version.
The [component Publish workflow](.github/workflows/publish.yml) downloads a
source/checksum-pinned native release and stages it transiently, without
rebuilding the native server. Legacy Intel macOS/Windows Resources stay checked in.

**Why native binaries are not committed:** the verified v4.12.1 macOS arm64
server is **190,504,960 bytes (181.68 MiB)**, over GitHub's 100 MiB file limit.
The approved strategy is **pinned native release reuse**, not an oversized Git
commit or implicit LFS migration. No `server-*` release exists as of 2026-11-02.
The component lock is explicitly unconfigured: **Publish will fail before versioning
until a validated native release is published and its exact lock is adopted**.
It never falls back to latest or silently packages the legacy arm64 executable.

## Native server CLI

[Build workflow and downloadable CI artifacts](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml)
| [Published releases](https://github.com/miyako/LocalAI/releases)
| [Upstream source](https://github.com/mudler/LocalAI)

**Server-CLI-only** archives contain a source-built `bin/local-ai` and embedded
web UI, **not inference backends, model weights, Python environments or GPU
drivers**. A healthy empty server is not an inference-ready installation.
No upstream prebuilt server binary is downloaded.

### Version and platform policy

With an empty `upstream_ref`, the workflow uses
[`scripts/native/source-lock.json`](scripts/native/source-lock.json): an immutable
upstream commit and SHA-256 hashes of `go.mod`, `go.sum` and the UI npm lockfile.
It does **not** query latest or move to a newer engine automatically. One resolution
job passes that snapshot to the entire matrix.
Manual builds accept an exact `vX.Y.Z` tag (optional suffix) or full lowercase
40-character SHA to rebuild a specific source revision.

The source baseline verified on **2026-11-02** is **v4.12.1**,
[`ec9274027eadd552d56f2c6c1fe86cd9216a991a`](https://github.com/mudler/LocalAI/tree/ec9274027eadd552d56f2c6c1fe86cd9216a991a).
Default runs remain pinned until the source lock is deliberately reviewed and
updated. Exact manual overrides resolve the requested source and lockfile bytes
once and record them in the artifacts. Component adoption independently locks
the exact published release, source snapshot and asset bytes.

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
Existing [CI run 41398850291](https://github.com/miyako/LocalAI/actions/runs/41398850291)
built and passed extracted CLI/HTTP smoke tests on all three native hosts.
Its downloaded macOS archive was independently checksum-verified and exercised
on macOS arm64 during this integration. That older run predates the new dependency
license collector/release-lock gates; it does not validate those new hosted
steps. No inference workload or 4D runtime was exercised.

### Build, download and install

Use **Actions > Build native LocalAI server > Run workflow**. The default
`publish=false` only builds, validates and uploads CI
artifacts. PRs and ordinary native-script pushes are read-only build validation.
To publish a separate server archive, explicitly dispatch on
`main` with `publish=true`; publishing waits for all three native smoke tests.
There is no scheduled publication. Server releases use unique
`server-<version>-<sha12>-<run-id>-<attempt>` tags and `--latest=false`, leaving
the latest 4D component release untouched. Re-runs never overwrite server assets.

Each CI artifact wraps one archive and its `.sha256` file. Published server
releases instead have three archives and a combined `SHA256SUMS`. Example name:

```text
local-ai-v4.12.1-ec9274027ead-darwin-arm64-server-cli-only.tar.gz
```

New archives contain `bin/local-ai`, upstream `LICENSE-LocalAI`, `PACKAGE.txt`,
`provenance.json` (upstream ref/SHA, builder SHA, tool versions, lock hashes,
binary hash, target and signing status), `build-info.txt`, a runtime dependency
audit, a dependency license/notice inventory and the source's Go/npm lock files.
The upstream license is exported from the immutable Git object. Dependency
license collection uses pinned `google/go-licenses/v2` v2.0.1 plus installed
production npm dependency metadata/license files; missing legal material fails
the build rather than being silently omitted. The only exception is an exact npm
name+version listed in `scripts/native/vendored-licenses/manifest.json`, which
supplies the real upstream LICENSE pinned by repository, commit and sha256. These are engineering completeness
checks, not a legal determination of redistribution rights.
Dependencies use upstream `go.sum`,
`npm ci`, and upstream-pinned protobuf generators. Tool versions are recorded;
source-pinned rebuilds are supported, **byte-for-byte reproducibility across
different toolchains/runners is not claimed**. Check upstream and dependency
licenses before redistribution; inference backend/model licenses are separate.
Go 1.26.0 and Node 22.23.4 are selected explicitly in CI; the local Go toolchain
must match the source requirements (`GOTOOLCHAIN=local`, no automatic upgrade).

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

Requirements: native supported host, Git, GitHub CLI, Python 3.11+, Go 1.26.0
(automatic toolchain upgrades disabled), Node.js 22.23.4 / npm,
Make, curl and unzip. macOS also needs Xcode Command Line Tools (`codesign`,
`otool`); Linux needs binutils (`readelf`). No CMake, llama static library,
Windows vcpkg or obsolete `llamacpp,tflite` Go tags are required for this server.
The upstream Makefile obtains protoc 31.1 and pinned Go protobuf plugins.
Network access and several GB of dependency/build cache space are required.

From a checkout of this repository:

```sh
python3 scripts/native/native.py resolve --output source.json
git clone --filter=blob:none --no-checkout https://github.com/mudler/LocalAI.git upstream
SHA=$(python3 -c 'import json; print(json.load(open("source.json"))["sha"])')
git -C upstream checkout --detach "$SHA"
bash scripts/native/build.sh upstream source.json dist
mkdir -p extracted
tar -xzf dist/*.tar.gz -C extracted
python3 scripts/native/native.py smoke extracted/bin/local-ai "$SHA" v4.12.1
```

Generated source files remain in the upstream checkout; dependency license
output is written to `dist/.native-licenses` (use a fresh output directory for
each build). Do not edit tracked upstream
sources before running the build helper. Unsupported manual revisions may fail
if upstream changes its build/CLI interfaces: the workflow deliberately fails
rather than patching upstream silently or publishing untested packages.

## 4D component

See [Pages usage](https://miyako.github.io/LocalAI/) and
[class documentation](LocalAI/Documentation/Classes/_LocalAI.md).
The 4D publishing workflow builds the component with the **exact native release
in `scripts/native/component-lock.json`**, never latest and never a native rebuild.
Downloads are validated outside the worktree before versioning. The verified
macOS arm64 executable and its license/provenance tree are overlaid into Resources
only after clean-tree versioning, then packaged. They are never added to Git.
Existing
Windows/Intel component resources remain legacy,
best-effort launch paths; they are not new v4.12.1 builds or part of the native
server matrix above. Do not copy a Linux binary into Windows component resources.
Their exact upstream server versions are not established by this update; neither
the component version nor an executable filename identifies the server version.

### Maintainer run order and Git writes

1. Run **Build native LocalAI server** with default options for read-only
   build validation. Native compilation/UI generation took roughly 4-7 minutes
   per target in the prior successful run, plus runner queue/download time.
   Allow up to 90 minutes per target; dependency license collection adds work
   and has not yet been measured on hosted runners.
2. Separately authorize native publication, then manually dispatch on **main**
   with `publish=true`. All three native targets must succeed. The integration validates exact
   source/builder identity, source locks, actual binary format/architecture,
   dependency audits, license inventories, smoke receipts and all file/archive
   hashes. A trusted `contents: write` job creates a unique `server-*` release
   with `--latest=false`; no repository resources are committed. Main must still
   equal the dispatch SHA. PRs cannot enter this job.
3. Adopt that exact published tag locally:
   `python3 scripts/native/release.py adopt --tag EXACT_SERVER_TAG`.
   The command downloads and validates **all three targets**, then writes only
   `scripts/native/component-lock.json`. Review and commit that small text lock
   through the normal authorized review process. It pins release ID/tag,
   builder commit, asset IDs/sizes/SHA-256 and the full source/dependency-lock
   snapshot. A missing, partial, moved or replaced release fails adoption.
   CI artifacts from the older run are not suitable substitutes for this
   published, license-complete release.
4. Separately dispatch **Publish** on main with the desired version increment.
   It downloads the pinned four release assets, rechecks identities and all
   checksums/provenance, validates the extracted macOS signature and runs the
   actual isolated CLI/HTTP smoke **before** the existing version-bump action.
   Downloads/staging live under runner temporary directories, keeping Git clean.
   After versioning, the verified arm64 resource and native metadata/licenses
   are copied transiently into `LocalAI/Resources/`; package Resources are checked
   again before signing. An independent structured 4D compilation report must show
   `success: true` and no diagnostics, and the compiled `.4DZ`/`.4dz` must be a
   nonempty valid standard ZIP; the external packaging action's exit code alone
   is insufficient. Both hosted and self-hosted Publish paths use these gates.
   The publishing host must be macOS arm64; legacy Intel/Windows payloads remain
   byte-for-byte unchanged. No native compiler, Go or npm server build is invoked.

The native workflow never dispatches component Publish and needs no
`actions: write` permission. A `GITHUB_TOKEN` push would not trigger another push
workflow; this design does not rely on that behavior or a bot resource commit.
Lock-only adoption does not trigger automatic component publication. Human pushes
matching 4D sources or `LocalAI/Resources/**` retain ordinary Publish behavior
using the already adopted native lock. Native publication and component Publish
share concurrency and reject stale main snapshots. Component versioning retains
the existing version action; no new Git staging, force pushes or history rewriting
is introduced by native integration.

Current checked-in resources versus actual CI build sizes:

| Executable | Checked in (bytes) | CI v4.12.1 (bytes) |
|---|---:|---:|
| macOS arm64 `local-ai` | 92,905,152 | 190,504,960; transient release input only |
| macOS Intel `local-ai-x86_64` | 98,261,936 | Not rebuilt; retained |
| Windows `local-ai.exe` | 98,194,944 | Not rebuilt; retained |
| Linux amd64 (standalone only) | Not bundled | 196,493,474 |
| Linux arm64 (standalone only) | Not bundled | 184,811,682 |

Archive compression does not reduce the Git blob size of an extracted executable.
The existing resources have no established upstream version/provenance.
An initial legacy checkout is accepted only as a base for the mandatory locked
arm64 overlay; an unconfigured/missing release lock never bypasses that overlay.
No suitable `server-*` release is currently published, so **bootstrap native
publication and lock adoption are required before the next component Publish**.
The new release transport/source-to-package path has fixture integration coverage,
not an updated hosted build or an actual 4D publication. A real downloaded prior
CI macOS executable passed local smoke tests; that is separate evidence.
The new compilation-report guard is fixture-tested but has not run in 4D here.
Existing 4D dependency resolution and Developer ID signing actions are not
reproducible dependency/signing attestations; this native integration does not
claim to validate a published signed component.

For manual installations outside this pinned component-publishing strategy, a bundled
resource takes precedence over
`PATH`. Check that `file LocalAI/Resources/bin/macOS/local-ai` reports ARM64 and
its `--help` output contains the version/full SHA from the archive's provenance.
Modern-only options must not be passed to an unchanged legacy executable.
The [class guide](LocalAI/Documentation/Classes/_LocalAI.md) distinguishes generic
legacy-compatible usage from replacement-specific options. Empty backend/model
collections select the component's downloadable defaults, not offline operation;
installation callbacks do not establish server readiness. Do not try to commit
the current oversized replacement. Resource hashes describe the source-built,
ad-hoc-signed **pre-component-signing** bytes. Publish's existing Developer ID
signing can change packaged executable bytes; these hashes are not a final
signed-component checksum or proof of 4D compilation/notarization success.

## Validation helpers

```sh
python3 -m unittest discover -s scripts/native -p 'test_*.py' -v
shellcheck scripts/native/build.sh
actionlint .github/workflows/build-server.yml .github/workflows/publish.yml
python3 scripts/native/resources.py verify --allow-legacy
```
