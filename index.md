---
layout: default
---

![version](https://img.shields.io/badge/version-20%2B-E23089)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/LocalAI)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/LocalAI/total)

# Use LocalAI from 4D

#### Abstract

[LocalAI](https://github.com/mudler/LocalAI) is a modular ecosystem designed to locally run multiple AI models and backends. It primarily targets Linux, Docker or Windows Subsystem for Linux, but native macOS and Windows distribution is also possible with limited choice of backends.

- llama.cpp
- stable-diffusion.cpp
- whisper
- piper
- etc

#### Usage

Instantiate `cs.LocalAI.server` and call `.start()` in your *On Startup* database method:

```4d
#DECLARE($params : Object)

Case of 
    : (Count parameters=0)
        
        CALL WORKER(1; Current method name; {})
        
    Else 
        
        var $LocalAI : cs.LocalAI.models
        $LocalAI:=cs.LocalAI.models.new()
        
        /*
            models_path: mandatory
            model: name of model to install
            data : string passed to callback in $2.content
            pass a subclass of _LocalAI_Controller to cs.models.new() above
            to process onData, onDataError, etc.
        */
        
        var $models : Collection
        $models:=[]
        $models.push({\
        model: "localai@nomic-embed-text-v1.5"; \
        data: "installed nomic-embed-text-v1.5"; \
        models_path: Folder(fk desktop folder).folder("models")})
        
        $LocalAI.install($models; Formula(onModelInstall))
        
End case 
```

Unless the server is alraedy running (in which case the costructor does nothing), the following procedure runs in the background:

1. The specified model is download via HTTP
2. The `local-ai` program is started

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

The API is compatibile with [Open AI](https://platform.openai.com/docs/api-reference/embeddings). 

|Class|API|Availability|
|-|-|:-:|
|Models|`/v1/models`|✅|
|Chat|`/v1/chat/completions`|✅|
|Images|`/v1/images/generations`|✅|
|Moderations|`/v1/moderations`|✅|
|Embeddings|`/v1/embeddings`|✅|
|Files|`v1/files`|✅|
