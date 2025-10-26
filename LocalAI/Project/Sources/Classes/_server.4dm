Class extends _LocalAI

Class constructor($controller : 4D:C1709.Class)
	
	Super:C1705("server"; $controller)
	
Function run($option : Object) : 4D:C1709.SystemWorker
	
	var $command : Text
	$command:=This:C1470.escape(This:C1470.executablePath)
	
	Case of 
		: (Value type:C1509($option.models_path)=Is object:K8:27) && (OB Instance of:C1731($option.models_path; 4D:C1709.Folder)) && ($option.models_path.exists)
			$command+=" --models-path="
			$command+=This:C1470.escape(This:C1470.expand($option.models_path).path)
	End case 
	
	var $arg : Object
	var $valueType : Integer
	var $key : Text
	
	For each ($arg; OB Entries:C1720($option))
		Case of 
			: (["models_path"].includes($arg.key))
				continue
		End case 
		$valueType:=Value type:C1509($arg.value)
		$key:=Replace string:C233($arg.key; "_"; "-"; *)
		Case of 
			: ($valueType=Is real:K8:4)
				$command+=(" --"+$key+"="+String:C10($arg.value)+" ")
			: ($valueType=Is text:K8:3)
				$command+=(" --"+$key+"="+This:C1470.escape($arg.value)+" ")
			: ($valueType=Is boolean:K8:9) && ($arg.value)
				$command+=(" --"+$key+" ")
			Else 
				//
		End case 
	End for each 
	
	return This:C1470.controller.execute($command; $isStream ? $option.model : Null:C1517; $option.data).worker