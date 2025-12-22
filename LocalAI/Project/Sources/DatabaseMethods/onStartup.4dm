var $LocalAI : cs:C1710.LocalAI

If (False:C215)
	$LocalAI:=cs:C1710.LocalAI.new()  //default
Else 
	var $port : Integer
	
	var $event : cs:C1710.event.event
	$event:=cs:C1710.event.event.new()
/*
Function onError($params : Object; $error : cs.event.error)
Function onSuccess($params : Object; $models : cs.event.models)
Function onData($worker : 4D.SystemWorker; $params : Object)
Function onTerminate($worker : 4D.SystemWorker; $params : Object)
*/
	
	$event.onError:=Formula:C1597(ALERT:C41($2.message))
	$event.onSuccess:=Formula:C1597(ALERT:C41($2.models.extract("name").join(",")+" loaded!"))
	$event.onData:=Formula:C1597(MESSAGE:C88([$2.fileName; $2.percentage; "%"].join(" ")))
	$event.onTerminate:=Formula:C1597(LOG EVENT:C667(Into 4D debug message:K38:5; (["process"; $1.pid; "terminated!"].join(" "))))
	
	$port:=8080
	$models:=["localai@nomic-embed-text-v1.5"; "localai@llama-3.2-1b-instruct:q4_k_m"]
	
	var $backends : Collection
	$backends:=[]
	
	Case of 
		: (Is macOS:C1572) && (System info:C1571.processor="@Apple@")
			$backends.push("localai@metal-llama-cpp")
			$backends.push("localai@mlx")
			$backends.push("localai@diffusers")
		Else 
			$backends.push("localai@cpu-llama-cpp")
			$backends.push("localai@stable-diffusion.cpp")
	End case 
	
	var $HOME : 4D:C1709.Folder
	$HOME:=Folder:C1567(fk home folder:K87:24).folder(".LocalAI")
	
	$LocalAI:=cs:C1710.LocalAI.new($port; $backends; $models; $HOME; {\
		models_path: $HOME.folder("models"); \
		backends_path: $HOME.folder("backends"); \
		disable_web_ui: False:C215; \
		host: "127.0.0.1"; \
		threads: 4; \
		context_size: 2048}; $event)
	
End if 