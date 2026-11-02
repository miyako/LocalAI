#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 3 ]]; then
  echo "Usage: bash scripts/native/build.sh UPSTREAM_CHECKOUT SOURCE_JSON OUTPUT_DIR" >&2
  exit 2
fi

scripts="$(cd "$(dirname "$0")" && pwd)"
source_dir="$(cd "$1" && pwd)"
metadata="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
mkdir -p "$3"
output="$(cd "$3" && pwd)"
read -r sha version < <(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(d["sha"], d["version"])
' "$metadata")

cd "$source_dir"
test "$(git rev-parse HEAD)" = "$sha"
test -z "$(git status --porcelain --untracked-files=no)"
export CGO_ENABLED=0
export GOTOOLCHAIN=local
export GOFLAGS=-mod=readonly
unset GOOS GOARCH GOAMD64 GOARM64

# These are the server prerequisites from the upstream Makefile, not backend builds.
make protogen-go generate
(
  cd core/http/react-ui
  npm ci --no-audit --no-fund
  npm run build
)
go build -trimpath -buildvcs=false \
  -ldflags "-s -w -X github.com/mudler/LocalAI/internal.Version=$version -X github.com/mudler/LocalAI/internal.Commit=$sha" \
  -o local-ai ./cmd/local-ai
python3 "$scripts/licenses.py" "$source_dir" "$output/.native-licenses"

if [[ "$(uname -s)" == Darwin ]]; then
  codesign --force --sign - local-ai
  codesign --verify --strict local-ai
fi
python3 "$scripts/native.py" package "$source_dir" "$metadata" "$output" \
  --licenses "$output/.native-licenses"
