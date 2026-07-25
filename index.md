---
layout: default
---

![version](https://img.shields.io/badge/version-20%2B-E23089)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/LocalAI)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/LocalAI/total)

# Use LocalAI from 4D

#### Abstract

[LocalAI](https://github.com/mudler/LocalAI) is a modular ecosystem designed to locally run multiple AI models and backends. It primarily targets Linux, Docker or Windows Subsystem for Linux, but native macOS and Windows distribution is also possible with select backends.

#### Usage

Instantiate `cs.LocalAI.LocalAI` in your *On Startup* database method:

```4d
var $LocalAI : cs.LocalAI.LocalAI

If (False)
    $LocalAI:=cs.LocalAI.LocalAI.new()  //default
Else 
    var $port : Integer
    
    var $event : cs.event.event
    $event:=cs.event.event.new()
    /*
        Function onError($params : Object; $error : cs.event.error)
        Function onSuccess($params : Object; $models : cs.event.models)
        Function onData($worker : 4D.SystemWorker; $params : Object)
        Function onTerminate($worker : 4D.SystemWorker; $params : Object)
    */
    
    $event.onError:=Formula(ALERT($2.message))
    $event.onSuccess:=Formula(ALERT($2.models.extract("name").join(",")+" loaded!"))
    $event.onData:=Formula(MESSAGE([$2.fileName; $2.percentage; "%"].join(" ")))
    $event.onTerminate:=Formula(LOG EVENT(Into 4D debug message; (["process"; $1.pid; "terminated!"].join(" "))))
    
    $port:=8080
    $models:=["localai@nomic-embed-text-v1.5"; "localai@llama-3.2-1b-instruct:q4_k_m"]
    
    var $backends : Collection
    $backends:=[]
    
    Case of 
        : (Is macOS) && (System info.processor="@Apple@")
            $backends.push("localai@metal-llama-cpp")
            $backends.push("localai@mlx")
            $backends.push("localai@diffusers")
        Else 
            $backends.push("localai@cpu-llama-cpp")
            $backends.push("localai@stable-diffusion.cpp")
    End case 
    
    var $HOME : 4D.Folder
    $HOME:=Folder(fk home folder).folder(".LocalAI")
    
    $LocalAI:=cs.LocalAI.LocalAI.new($port; $backends; $models; $HOME; {\
    models_path: $HOME.folder("models"); \
    backends_path: $HOME.folder("backends"); \
    disable_web_ui: False; \
    host: "127.0.0.1"; \
    threads: 4; \
    context_size: 2048}; $event)
    
End if 
```

Unless the server is already running (in which case the costructor does nothing), the following procedure runs in the background:

1. The specified model is downloaded via HTTP
2. The specified backend is downloaded via HTTP
3. The `local-ai` program is started

Now you can test the server:

```
curl -X POST http://127.0.0.1:8080/v1/embeddings \
     -H "Content-Type: application/json" \
     -d '{"input":"The quick brown fox jumps over the lazy dog."}'
```

Or, use AI Kit:

```4d
var $AIClient : cs.AIKit.OpenAI
$AIClient:=cs.AIKit.OpenAI.new()
$AIClient.baseURL:="http://127.0.0.1:8080/v1"

var $text : Text
$text:="The quick brown fox jumps over the lazy dog."

var $responseEmbeddings : cs.AIKit.OpenAIEmbeddingsResult
$responseEmbeddings:=$AIClient.embeddings.create($text)
```

Finally to terminate the server:

```4d
var $LocalAI : cs.LocalAI.server
$LocalAI:=cs.LocalAI.server.new()
$LocalAI.terminate()
```

#### AI Kit compatibility

The API is compatible with [Open AI](https://platform.openai.com/docs/api-reference/embeddings). 

|Class|API|Availability|
|-|-|:-:|
|Models|`/v1/models`|✅|
|Chat|`/v1/chat/completions`|✅|
|Images|`/v1/images/generations`|✅|
|Moderations|`/v1/moderations`|✅|
|Embeddings|`/v1/embeddings`|✅|
|Files|`/v1/files`|✅|
