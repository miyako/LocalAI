# local-ai
Local inference engine

## install Protocol Buffers Compiler `protoc`

* macOS
 
```
brew install protobuf
```

* Windows

```
vcpkg install protobuf --triplet x64-windows
```

## install golang dependencies

```
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
export PATH=$PATH:$(go env GOPATH)/bin
```

## set environment

* macOS

```
export LLAMA_LIB=libllama.a
export LLAMA_INCLUDE=llama.cpp-master 
```

* Windows

```
set LLAMA_LIB=llama.lib
set LLAMA_INCLUDE=llama.cpp-master
```
