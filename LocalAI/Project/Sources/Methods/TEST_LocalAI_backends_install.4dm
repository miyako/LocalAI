//%attributes = {"invisible":true}
#DECLARE($params : Object)

Case of 
	: (Count parameters:C259=0)
		
		CALL WORKER:C1389(1; Current method name:C684; {})
		
	Else 
		
		var $LocalAI : cs:C1710.backends
		$LocalAI:=cs:C1710.backends.new()
		
/*
backends_path: mandatory
backend: name of backend to install
data : string passed to callback in $2.content 
pass a subclass of _LocalAI_Controller to cs.backends.new() above 
to process onData, onDataError, etc.
*/
		
		var $backends : Collection
		$backends:=[]
		
		Case of 
			: (Is macOS:C1572) && (Not:C34(Get system info:C1571.macRosetta))
				$backends.push({\
					backend: "localai@metal-llama-cpp"; \
					data: "installed metal-llama-cpp"; \
					backends_path: Folder:C1567(fk desktop folder:K87:19).folder("backends")})
			Else 
				$backends.push({\
					backend: "localai@cpu-llama-cpp"; \
					data: "installed cpu-llama-cpp"; \
					backends_path: Folder:C1567(fk desktop folder:K87:19).folder("backends")})
		End case 
		
		$LocalAI.install($backends; Formula:C1597(onInstall))
		
End case 