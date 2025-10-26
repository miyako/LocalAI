Class extends _LocalAI

Class constructor
	
	Super:C1705($controller)
	
Function list() : Collection
	
	var $models : Collection
	$models:=[]
	
	var $command : Text
	$command:=This:C1470.escape(This:C1470.executablePath)
	$command+=" models list "
	
	var $worker : 4D:C1709.SystemWorker
	$worker:=This:C1470.controller.execute($command).worker
	$worker.wait()
	
	var $resultText : Text
	$resultText:=This:C1470.controller.stdOut
	
	ARRAY LONGINT:C221($pos; 0)
	ARRAY LONGINT:C221($len; 0)
	
	var $i : Integer
	$i:=1
	
	While (Match regex:C1019("(?m)^\\s*-\\s*(.+)$"; $resultText; $i; $pos; $len))
		$models.push(Substring:C12($resultText; $pos{1}; $len{1}))
		$i:=$pos{0}+$len{0}
	End while 
	
	return $models
	
Function install($option : Variant; $formula : 4D:C1709.Function) : Collection
	
	var $stdOut; $isStream; $isAsync : Boolean
	var $options : Collection
	var $results : Collection
	$results:=[]
	
	Case of 
		: (Value type:C1509($option)=Is object:K8:27)
			$options:=[$option]
		: (Value type:C1509($option)=Is collection:K8:32)
			$options:=$option
		Else 
			$options:=[]
	End case 
	
	var $commands : Collection
	$commands:=[]
	
	If (OB Instance of:C1731($formula; 4D:C1709.Function))
		$isAsync:=True:C214
		This:C1470.controller.onResponse:=$formula
	End if 
	
	For each ($option; $options)
		
		If ($option=Null:C1517) || (Value type:C1509($option)#Is object:K8:27)
			continue
		End if 
		
		$stdOut:=Not:C34(OB Instance of:C1731($option.output; 4D:C1709.File))
		
		$command:=This:C1470.escape(This:C1470.executablePath)
		$command+=" models install "
		
		If (Value type:C1509($option.model)=Is text:K8:3) && ($option.model#"")
			$command+=" "
			$command+=This:C1470.escape($option.model)
			$command+=" "
		Else 
			continue  //mandatory
		End if 
		
		If (Value type:C1509($option.models_path)=Is object:K8:27) && (OB Instance of:C1731($option.models_path; 4D:C1709.Folder))
			$command+=" --models-path="
			$command+=This:C1470.escape(This:C1470.expand($option.models_path).path)
		Else 
			continue  //mandatory
		End if 
		
		If (Value type:C1509($option.backends_path)=Is object:K8:27) && (OB Instance of:C1731($option.backends_path; 4D:C1709.Folder))
			$command+=" --backends-path="
			$command+=This:C1470.escape(This:C1470.expand($option.backends_path).path)
		Else 
			continue  //mandatory
		End if 
		
		var $arg : Object
		var $valueType : Integer
		var $key : Text
		
		For each ($arg; OB Entries:C1720($option))
			Case of 
				: (["data"; "model"; "models_path"; "backends_path"].includes($arg.key))
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
		
		var $worker : 4D:C1709.SystemWorker
		$worker:=This:C1470.controller.execute($command; Null:C1517; $option.data).worker
		
		If (Not:C34($isAsync))
			$worker.wait()
		End if 
		
		If ($stdOut) && (Not:C34($isAsync))
			//%W-550.26
			//%W-550.2
			$results.push(This:C1470.controller.stdOut)
			This:C1470.controller.clear()
			//%W+550.2
			//%W+550.26
		End if 
		
	End for each 
	
	If ($stdOut) && (Not:C34($isAsync))
		return $results
	End if 