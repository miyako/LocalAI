property options : Object

Class constructor($port : Integer; $backends : Collection; $models : Collection; $HOME : 4D:C1709.Folder; $options : Object; $event : cs:C1710.event.event)
	
	This:C1470.options:=$options#Null:C1517 ? $options : {}
	
	If (Value type:C1509(This:C1470.options.host)#Is text:K8:3) || (This:C1470.options.host="")
		This:C1470.options.host:="127.0.0.1"
	End if 
	
	var $LocalAI : cs:C1710.workers.worker
	$LocalAI:=cs:C1710.workers.worker.new(cs:C1710._server)
	
	If (Not:C34($LocalAI.isRunning($port)))
		
		If ($backends=Null:C1517) || ($backends.length=0)
			Case of 
				: (Is macOS:C1572) && (System info:C1571.processor="@Apple@")
					$backends:=["localai@metal-llama-cpp"]
				Else 
					$backends:=["localai@cpu-llama-cpp"]
			End case 
		End if 
		
		If ($models=Null:C1517) || ($models.length=0)
			$models:=["localai@nomic-embed-text-v1.5"; "localai@llama-3.2-1b-instruct:q4_k_m"]
		End if 
		
		If (Not:C34(OB Instance of:C1731($HOME; 4D:C1709.Folder))) || (Not:C34($HOME.exists))
			$HOME:=Folder:C1567(fk home folder:K87:24).folder(".LocalAI")
		End if 
		
		If ($port=0) || ($port<0) || ($port>65535)
			$port:=8080
		End if 
		
		This:C1470.options.backends:=$backends
		This:C1470.options.models:=$models
		This:C1470.options.port:=$port
		This:C1470.options.HOME:=$HOME
		
		This:C1470._main($port; $backends; $models; $HOME; $options; $event)
		
	End if 
	
Function _onTCP($status : Object; $options : Object)
	
	If ($status.success)
		
		var $className : Text
		$className:=Split string:C1554(Current method name:C684; "."; sk trim spaces:K86:2).first()
		
		CALL WORKER:C1389($className; Formula:C1597(start); $options)
		
	Else 
		
		var $statuses : Text
		$statuses:="TCP port "+String:C10($status.port)+" is aready used by process "+$status.PID.join(",")
		var $error : cs:C1710.event.error
		$error:=cs:C1710.event.error.new(1; $statuses)
		
		If ($options.event#Null:C1517) && (OB Instance of:C1731($options.event; cs:C1710.event.event))
			$options.event.onError.call(This:C1470; $options; $error)
		End if 
		
	End if 
	
Function _main($port : Integer; $backends : Collection; $models : Collection; $HOME : 4D:C1709.Folder; $options : Object; $event : cs:C1710.event.event)
	
	main({port: $port; backends: $backends; models: $models; HOME: $HOME; options: $options; event: $event}; This:C1470._onTCP)
	
Function terminate()
	
	var $LocalAI : cs:C1710.workers.worker
	$LocalAI:=cs:C1710.workers.worker.new(cs:C1710._server)
	$LocalAI.terminate()
	