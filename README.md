![version](https://img.shields.io/badge/version-20%2B-E23089)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/LocalAI)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/LocalAI/total)

# LocalAI
Local inference engine

## Install Protocol Buffers Compiler `protoc`

* macOS
 
```
brew install protobuf
export PATH=$PATH:$(go env GOPATH)/bin
```

* Windows

```
vcpkg install protobuf --triplet x64-windows
```

Make sure `PATH` finds `protoc`

## install golang dependencies

```
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
```

## set environment

* macOS

```
export LLAMA_LIB=libllama.a
export LLAMA_INCLUDE=llama.cpp-master 
mkdir -p pkg/grpc/proto
protoc --experimental_allow_proto3_optional \
  -Ibackend/ \
  --go_out=pkg/grpc/proto/ \
  --go_opt=paths=source_relative \
  --go-grpc_out=pkg/grpc/proto/ \
  --go-grpc_opt=paths=source_relative \
  backend/backend.proto
GOARCH=arm64 go build -tags "llamacpp,tflite" -o localai_arm64 ./cmd/local-ai/main.go
GOARCH=amd64 go build -tags "llamacpp,tflite" -o localai_amd64 ./cmd/local-ai/main.go
```

* Windows

```
set LLAMA_LIB=llama.lib
set LLAMA_INCLUDE=llama.cpp-master
mkdir -p pkg\grpc\proto
protoc --experimental_allow_proto3_optional -Ibackend --go_out=pkg\grpc\proto --go_opt=paths=source_relative --go-grpc_out=pkg\grpc\proto --go-grpc_opt=paths=source_relative backend\backend.proto
go build -tags "llamacpp" -o local-ai.exe .\cmd\local-ai\main.go
```
