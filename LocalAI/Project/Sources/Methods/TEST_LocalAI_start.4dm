//%attributes = {"invisible":true}
var $LocalAI : cs:C1710.server
$LocalAI:=cs:C1710.server.new()

$isRunning:=$LocalAI.isRunning()

/*
mandatory
models_path,backends_path
*/

$LocalAI.run({\
models_path: Folder:C1567(fk desktop folder:K87:19).folder("models"); \
backends_path: Folder:C1567(fk desktop folder:K87:19).folder("backends"); \
disable_web_ui: False:C215; \
address: "127.0.0.1:8080"; \
threads: 4; \
context_size: 2048})