---
layout: default
---

# LocalAI: native server and 4D integration

[LocalAI](https://github.com/mudler/LocalAI) exposes local models through
OpenAI-compatible APIs. This repository provides **source-built native server
CLI archives** and a **separate 4D 20+ component** that manages an installed
server. Installing the CLI alone does not install an inference engine or model.

[Get server build artifacts](https://github.com/miyako/LocalAI/actions/workflows/build-server.yml)
| [Browse releases](https://github.com/miyako/LocalAI/releases)
| [Full build and installation guide](https://github.com/miyako/LocalAI#native-server-cli)
| [4D class documentation](https://github.com/miyako/LocalAI/blob/main/LocalAI/Documentation/Classes/_LocalAI.md)

## What is built

The server workflow loads the checked-in **source-lock.json** (immutable commit
and Go/npm dependency-lock hashes), then builds every target from that same source.
It does not automatically track latest. An exact tag or full commit SHA can be
supplied manually and resolved once for the matrix. The pinned baseline
(2026-11-05) is the unreleased upstream master commit
[`c9b5d0ff5cfaa34f3ad3f387d5d79bc471588f23`](https://github.com/mudler/LocalAI/tree/c9b5d0ff5cfaa34f3ad3f387d5d79bc471588f23)
(`sha-c9b5d0ff5cfa`), because no tagged release yet drops an unlicensed transitive
dependency that v4.12.1 still includes.
This is not the 4D component's version.

| Archive target | Native build runner | Scope |
|---|---|---|
| `darwin-arm64` | macOS 15 / Apple Silicon | Server CLI + embedded web UI; ad-hoc signed, not notarized |
| `linux-amd64` | Ubuntu 24.04 / x86-64 | Static, CGO-disabled server CLI + web UI |
| `linux-arm64` | Ubuntu 24.04 / ARM64 | Same, built and exercised natively |

All three targets passed existing CI run
[41398850291](https://github.com/miyako/LocalAI/actions/runs/41398850291);
that run predates the new license/release-lock gates. These are not claims
that all inference backends work on every platform. Intel macOS and native Windows are excluded, matching
upstream's current server release scope. A Linux package may be used **inside
WSL2**, not as a native Windows executable or a drop-in Windows 4D worker.

## Download and start

Use the **Build native LocalAI server** Actions workflow for CI artifacts,
or select a published release whose tag begins with **`server-`**. Server release
publishing is an explicit manual option and does not replace the latest 4D
component release. Adding the workflow does not itself publish any binaries.

An example archive name is:

```text
local-ai-sha-c9b5d0ff5cfa-c9b5d0ff5cfa-darwin-arm64-server-cli-only.tar.gz
```

Select the version, SHA and target actually listed in the chosen release.
Verify the archive against `SHA256SUMS` (or its CI `.sha256` companion) before
extraction. The archive has `bin/local-ai`, upstream license, dependency audit,
source lock files and version/build provenance. It has **no inference backends,
model weights, Python environments or GPU drivers**.

After following the [download/checksum instructions](https://github.com/miyako/LocalAI#build-download-and-install),
extract to `localai-server`, then:

```sh
mkdir -p "$HOME/.localai-native"/{models,backends}
SERVER="$PWD/localai-server/bin/local-ai"
cd "$HOME/.localai-native"
"$SERVER" run --address 127.0.0.1:8080 \
  --models-path "$PWD/models" --backends-path "$PWD/backends"
```

In another terminal:

```sh
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/readyz
curl --fail http://127.0.0.1:8080/v1/models
```

The web UI is at `http://127.0.0.1:8080/`. Keep the server on loopback unless
authentication and access controls have been configured. macOS downloads are
not Developer ID signed/notarized; use your organization's approval policy or
build from source if Gatekeeper blocks execution.

## Enable inference

Use `local-ai backends list` and `local-ai models list` to inspect the current
galleries; consult each `install --help` subcommand and
[upstream backend documentation](https://localai.io/backends/) before installing.
Set the same `LOCALAI_MODELS_PATH` and `LOCALAI_BACKENDS_PATH` for installation
and server runs. Gallery installation requires network access. Backend/platform
compatibility, Python/uv environments, shared libraries, CPU features and GPU
drivers are **independent of the server binary**. Backend/model licensing and
version pinning also need separate review.

Once an embedding model is installed and loaded, use its actual model ID from
`/v1/models`:

```sh
curl --fail http://127.0.0.1:8080/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"model":"YOUR_INSTALLED_EMBEDDING_MODEL_ID","input":"The quick brown fox jumps over the lazy dog."}'
```

Endpoint availability depends on the loaded model and its backend. An empty
model list or a successful health probe does not establish inference support.

## Use from 4D

Component **Publish reuses a pinned native release without rebuilding the server**.
The native workflow's separately authorized `publish=true` option creates a
validated complete three-target `server-*` release, never replacing the latest
component release. Adopt its exact tag with `scripts/native/release.py adopt`;
review and commit only the generated small release lock. Component Publish
downloads that exact release and validates source/builder identity, asset
IDs/sizes/checksums, runtime dependencies, licenses and native smoke evidence.

**Why use release assets rather than Git binaries?** The actual v4.12.1 macOS executable is
**190,504,960 bytes (181.68 MiB)**, exceeding GitHub's 100 MiB file limit.
The approved solution stages its validated executable/license/provenance tree
transiently into Resources **after clean-tree component versioning**; it never
commits the oversized binary or introduces LFS. Legacy Windows/Intel resources
are preserved unchanged; Linux remains standalone.

**Bootstrap required:** no `server-*` release exists as of 2026-11-02. Publish
fails before versioning until a license-complete native release is published
and its exact release lock is adopted. There is no latest or legacy fallback.
After lock adoption, separately dispatch **Publish** on main. The native
workflow does not dispatch component publication. A `GITHUB_TOKEN` push would not
trigger push workflows; no such resource commit is used here. Human pushes to
component sources/resources retain ordinary Publish behavior using the pinned
release. Both workflows share concurrency and reject stale main snapshots.
Default native builds/PRs are read-only.
Follow the
[class installation and platform instructions](https://github.com/miyako/LocalAI/blob/main/LocalAI/Documentation/Classes/_LocalAI.md)
before using its launcher. The detailed class guide includes constructor
parameters, model/backend installation callbacks and termination.

Existing Windows/Intel launcher paths and executable resources are retained as
legacy best-effort behavior, not current source-built server support. For the
new server via the macOS arm64 launcher, a validated replacement is required;
do not try to commit the current oversized archive's executable.
Bundled resources take precedence over `PATH`; modern-only
flags must not be passed to unchanged legacy binaries. Empty backend/model
collections select downloadable defaults, not offline mode.

For AI Kit, point an OpenAI client at an already running, configured server:

```4d
var $AIClient : cs.AIKit.OpenAI
$AIClient:=cs.AIKit.OpenAI.new()
$AIClient.baseURL:="http://127.0.0.1:8080/v1"
```

Choose the installed model explicitly in your AI Kit request; the server does
not choose an embedding model merely because the request contains text.
Use Linux/WSL as a separately managed HTTP server rather than placing its binary
in Windows component resources.

## Maintainer build and verification

The [GitHub guide](https://github.com/miyako/LocalAI#build-locally-from-the-same-source)
documents local source builds, pinned source overrides and tool prerequisites.
The workflow builds the embedded React UI using the upstream npm lockfile,
generates protobufs with upstream-pinned tools, and compiles `./cmd/local-ai`
without obsolete `llamacpp,tflite` build tags. Before artifacts are uploaded,
the **extracted package** is checked for expected version/SHA, runtime
dependencies, CLI help, HTTP liveness/readiness, empty model listing and web UI.
New packages also require dependency license/notice closure and per-file hashes.
Native builds previously took 4-7 minutes per target plus runner queue time;
the new licensing steps have not yet been timed on hosted runners. Component-only
Publish avoids that native work. Resource inventories cover pre-component-signing
bytes, not the final signed component. See the
[maintainer run order and size evidence](https://github.com/miyako/LocalAI#maintainer-run-order-and-git-writes)
for the exact Git-write/publication gates and validation limitations.
