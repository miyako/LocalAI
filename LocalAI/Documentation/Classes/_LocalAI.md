# _LocalAI : _CLI

`_LocalAI` is a subclass of `_CLI` to execute `local-ai`.

## Native server distribution

The modern server target is **mudler/LocalAI v4.12.1**, not a Go library embedded in 4D.
The component also retains best-effort execution of its legacy resource binaries.
Forthcoming native artifacts are **server-only** `tar.gz` archives with
archive-root `bin/local-ai`, provenance and license material. The target platforms
are **only macOS arm64 and Linux amd64/arm64**, matching upstream's
[`.goreleaser.yaml`](https://github.com/mudler/LocalAI/blob/v4.12.1/.goreleaser.yaml);
macOS amd64 is explicitly excluded. An archive is not a 4D
component, and does not include model weights or promise bundled inference
backends, GPU libraries, Python environments, or working inference on every target.
Backend installation remains a separate, platform-dependent operation.

For the pinned v4.12.1 source, an example archive name is
`local-ai-v4.12.1-ec9274027ead-darwin-arm64-server-cli-only.tar.gz`.
Select the actual version, source SHA and target in the chosen release.
The separate server workflow does not inject executable resources into the 4D
component, and its releases do not replace the latest 4D component release.

The checked-in resource executables are legacy binaries, not newly built or
verified v4.12.1 artifacts. Replace the executable before using this integration
with v4.12.1 or passing modern-only flags; do not infer its version from its filename.
The bundled arm64 executable accepts the common flags below, but its `--version`
output is blank and it rejects `--disable-local-ai-assistant`. Legacy Windows and
Intel resources have not been runtime-validated here.
The exact LocalAI versions of all three checked-in executables are unknown.
Their filenames and Go compiler metadata do not establish an upstream version.

### macOS arm64 with 4D

1. Obtain the matching source-built server archive and verify its provenance/checksum
   according to the release instructions. Retain its license material.
2. Extract it outside the component, then copy `bin/local-ai` to
   `LocalAI/Resources/bin/macOS/local-ai` before packaging the component. This is
   an explicit deployment step: the 4D resolver does not unpack archives.
3. Before deployment, inspect the extracted `bin/local-ai` with `file`: it must
   be a Mach-O arm64 executable, not an Intel Mach-O, ELF Linux binary or Windows
   executable. Verify the archive's provenance identifies the intended source
   version and commit. Run that exact executable with `--version`: require
   nonempty version/commit output matching the source-built archive, not merely
   exit code zero (the legacy arm64 resource returns a blank version). For the
   pinned example, expect v4.12.1 and commit
   `ec9274027eadd552d56f2c6c1fe86cd9216a991a`, or its displayed short prefix.
   Run `run --help` and confirm every option you intend to pass is supported.
   `_CLI` restores the executable bit when 4D transfers resource files. The
   archive's dependencies and macOS trust requirements still apply; `chmod` is
   not signing or notarization.
4. Alternatively remove the resource executable and install the matching
   `local-ai` on the 4D process's `PATH`. A resource executable always takes
   precedence over `PATH`.

The historical resolver is preserved: Apple Silicon uses
`Resources/bin/macOS/local-ai`, Intel Macs use
`Resources/bin/macOS/local-ai-x86_64`, and Windows uses
`Resources/bin/Windows/local-ai.exe`. Existing files take precedence over `PATH`;
the fallback names are respectively `local-ai`, `local-ai-x86_64` and
`local-ai.exe`. There is no unconditional Windows/Intel launch gate and no new
executable-selection API. Legacy launcher capability is independent of the new
artifact matrix: retaining it does not claim v4.12.1 native support on those
platforms. Do not copy the modern arm64 executable over an Intel resource.
The resolver does not inspect executable versions or architectures and does not
silently convert legacy resources into modern builds. These manual verification
requirements also apply to executables selected through `PATH`; verify the
executable visible to the 4D process, not a different terminal installation.

### Linux and Windows

Linux server archives can run independently on their matching architecture.
Their availability does **not** make this component a Linux 4D runtime or add
Linux process-launch support to `_CLI`. Operate Linux servers externally and
connect an HTTP/OpenAI-compatible client to their configured endpoint.

There is **no native Windows v4.12.1 distribution until supported upstream**.
The historical `Resources/bin/Windows/local-ai.exe`, generic `.exe` lookup and
Windows quoting helper are legacy implementation details, not a supported
modern server/backend combination. Existing Windows executable lookup and
argument quoting are preserved for best-effort legacy operation, without
claiming compatibility with modern-only flags or backends.
For the modern server, use an externally managed Linux/WSL2/container server
on Windows; the component does not start WSL, translate Windows paths to WSL, or
manage a remote server. Never pass an ELF Linux executable to Windows
`SystemWorker` or rename it to `.exe`.

## Public lifecycle

`cs.LocalAI.LocalAI.new($port; $backends; $models; $HOME; $options; $event)`
from an installed component (`cs.LocalAI.new(...)` inside this project) retains
the existing defaults: loopback port 8080, a platform-selected llama.cpp gallery
backend, and the two example gallery models. Empty backend/model collections
still select those defaults, rather than requesting no downloads. Gallery
availability and backend compatibility must be verified separately.
This preserves the download/install behavior; the default constructor is not an
offline or inference-ready mode. Gallery operations require network access.

Minimal installed-component usage with no modern-only options:

```4d
var $LocalAI : cs.LocalAI.LocalAI
$LocalAI:=cs.LocalAI.LocalAI.new(8080; []; []; Null; {host: "127.0.0.1"}; Null)
```

Retain the instance if it will be used to call `$LocalAI.terminate()` later; do
not construct another launcher merely to terminate it. The standalone project's
exit method terminates the managed workers directly.

The constructor normalizes the port before checking running workers, defaults
missing options to an object, creates the requested home folder even if it is
new, and defaults `models_path`/`backends_path` below that folder. Existing folder
objects supplied by the caller are retained.
Already-managed workers are reused before storage setup, installation or TCP
availability checks, regardless of platform. Independently managed local or
remote HTTP servers are not attached by this constructor; use an HTTP client.

After the TCP availability check, installation executes sequentially in a 4D
worker. Installed entries are skipped; successful installs notify `onSuccess`.
Only after all requested installs succeed is the server registered and started
through `cs.workers.worker`. Nonzero installation exits set `installFailed`,
notify `onError` when available, and prevent startup. The exit database method
terminates managed workers directly, without accidentally starting a server.
Installation failures, invalid start folders and occupied-port errors are
reported through `onError` when supplied, or to the 4D debug log otherwise.

`onSuccess` means an installation step completed or an entry was already
installed. It does **not** mean the HTTP server is ready or a model was loaded
for inference. Confirm readiness separately against the running server before
issuing requests. `onData` reports best-effort CLI download progress from stdout
or stderr; it is not a stable structured progress API. `onTerminate` is forwarded
for the server process.

## CLI compatibility

Commands and flags were checked read-only against the pinned upstream sources:

- [`core/cli/cli.go`](https://github.com/mudler/LocalAI/blob/v4.12.1/core/cli/cli.go):
  explicit `local-ai run`.
- [`core/cli/run.go`](https://github.com/mudler/LocalAI/blob/v4.12.1/core/cli/run.go):
  `--address=host:port`, `--models-path`, `--backends-path`,
  `--localai-config-dir`, `--threads`, `--context-size`, `--disable-web-ui`,
  and `--disable-local-ai-assistant`. Kong generates kebab-case flag names;
  for example the 4D option `disable_local_ai_assistant: True` emits
  `--disable-local-ai-assistant=true`, not `--disable-localai-assistant`.
  This modern-only option requires the validated source-built macOS arm64
  replacement described above; it is not included in bare defaults or the
  generic constructor example.
- [`core/cli/backends.go`](https://github.com/mudler/LocalAI/blob/v4.12.1/core/cli/backends.go):
  `backends list` / `backends install NAME --backends-path=PATH`.
- [`core/cli/models.go`](https://github.com/mudler/LocalAI/blob/v4.12.1/core/cli/models.go):
  `models list` / `models install NAME --models-path=PATH --backends-path=PATH`.
  Model installation can autoload a backend, so it must use the same backend
  directory as explicit backend installation and the server.

The installed-list parser accepts both `(installed)` and backend version/upgrade
suffixes, without including the version in the gallery identifier. Numeric
options accept integer and real values. Explicit boolean options are emitted
as `--flag=true` or `--flag=false`, preserving a caller's override of a
default-true upstream option. Component metadata is not emitted as CLI flags.
Pass only flags supported by the selected subcommand; arbitrary option names are
not validated against the upstream CLI.

## Validation boundary

Run the persistent stdlib checks with
`python3 -m unittest discover -s scripts/native -p test_component.py -v`.
They verify static source invariants and fixture transformations, not execution
of 4D methods.

Static inspection can check command construction, list-output fixtures,
escaping, source block balance and project metadata. It cannot compile 4D code,
execute 4D callbacks, verify worker event ordering, prove server readiness or
demonstrate inference. Before shipping, run the project in 4D on macOS arm64 with
the actual v4.12.1 server, exercise fresh/already-installed/failed installations,
verify all three storage directories, loopback binding, shutdown callbacks and
paths containing spaces/apostrophes, and test the selected backend/model
combination separately. No 4D engine or new server artifact is presumed here.
