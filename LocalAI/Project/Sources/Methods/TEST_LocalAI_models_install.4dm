//%attributes = {"invisible":true}
#DECLARE($params : Object)

Case of 
	: (Count parameters:C259=0)
		
		CALL WORKER:C1389(1; Current method name:C684; {})
		
	Else 
		
		var $LocalAI : cs:C1710.models
		$LocalAI:=cs:C1710.models.new()
		
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
			models_path: Folder:C1567(fk desktop folder:K87:19).folder("models")})
		
		$LocalAI.install($models; Formula:C1597(onInstall))
		
End case 