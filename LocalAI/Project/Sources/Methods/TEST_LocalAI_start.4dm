//%attributes = {"invisible":true}
var $LocalAI : cs:C1710.server
$LocalAI:=cs:C1710.server.new()

$isRunning:=$LocalAI.isRunning()

$folder:=Folder:C1567("Macintosh HD:Users:miyako:Documents:GitHub:4d-example-local-inference:local-inference:Resources:models:"; fk platform path:K87:2)

$LocalAI.run({\
models_path: $folder; \
disable_web_ui: False:C215; \
address: ":8080"; \
threads: 4; \
context_size: 2048})