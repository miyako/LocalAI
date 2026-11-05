property installFailed : Boolean

Class extends _LocalAI

Class constructor($controller : 4D:C1709.Class)
	
	If ($controller=Null:C1517)
		$controller:=cs:C1710._Normal_Controller
	End if
	Super:C1705($controller)
	
Function start($option : Object) : 4D:C1709.SystemWorker
	
	This:C1470.bind($option; ["onTerminate"; "onError"])

	var $command : Text
	$command:=This:C1470.escape(This:C1470.executablePath)+" run"
	
	If (Value type:C1509($option.models_path)=Is object:K8:27) && (OB Instance of:C1731($option.models_path; 4D:C1709.Folder))
		$command+=" --models-path="
		$command+=This:C1470.escape(This:C1470.expand($option.models_path).path)
	Else 
		This:C1470._error($option; 1; "LocalAI start requires models_path as a 4D.Folder.")
		return
	End if
	
	If (Value type:C1509($option.backends_path)=Is object:K8:27) && (OB Instance of:C1731($option.backends_path; 4D:C1709.Folder))
		$command+=" --backends-path="
		$command+=This:C1470.escape(This:C1470.expand($option.backends_path).path)
	Else 
		This:C1470._error($option; 1; "LocalAI start requires backends_path as a 4D.Folder.")
		return
	End if
	
	var $arg : Object
	var $valueType : Integer
	var $key : Text
	var $address : Text
	$address:=$option.host+":"+String:C10($option.port)
	$command+=" --address="+This:C1470.escape($address)
	
	For each ($arg; OB Entries:C1720($option))
		Case of 
			: (["address"; "host"; "port"; "models_path"; "backends_path"; "version"; "help"; "HOME"; "models"; "backends"; "data"; "event"; "onTerminate"; "onSuccess"; "onData"; "onError"].includes($arg.key))
				continue
		End case 
		$valueType:=Value type:C1509($arg.value)
		$key:=Replace string:C233($arg.key; "_"; "-"; *)
		Case of 
			: ($valueType=Is real:K8:4)
				$command+=(" --"+$key+"="+_argNumber($arg.value)+" ")
			: ($valueType=Is integer:K8:5)
				$command+=(" --"+$key+"="+String:C10($arg.value)+" ")
			: ($valueType=Is text:K8:3)
				$command+=(" --"+$key+"="+This:C1470.escape($arg.value)+" ")
			: ($valueType=Is boolean:K8:9)
				$command+=(" --"+$key+"="+($arg.value ? "true" : "false")+" ")
			Else 
				//
		End case 
	End for each 
	
	var $HOME : 4D:C1709.Folder
	$HOME:=$option.HOME
	If (Not:C34(OB Instance of:C1731($HOME; 4D:C1709.Folder)))
		This:C1470._error($option; 1; "LocalAI start requires HOME as a 4D.Folder.")
		return
	End if
	$HOME.create()
	
	$command+=(" --localai-config-dir "+This:C1470.escape($HOME.path)+" ")
	
	//The add-on runtime is Linux-only upstream and on by default. An environment
	//variable (not a flag) keeps legacy executables, which reject unknown flags, working.
	//An explicit addons_enabled option becomes a flag above and takes precedence.
	If (Undefined:C82($option.addons_enabled))
		This:C1470.controller.variables.LOCALAI_ADDONS_ENABLED:="false"
	End if 
	
	//SET TEXT TO PASTEBOARD($command)
	
	return This:C1470.controller.execute($command; Null:C1517; $option.data).worker

Function _error($params : Object; $code : Integer; $message : Text)

	If ($message="")
		$message:="LocalAI command failed with exit code "+String:C10($code)+"."
	End if
	If (OB Instance of:C1731(This:C1470.onError; 4D:C1709.Function))
		This:C1470.onError.call(This:C1470; $params; cs:C1710.event.error.new($code; $message))
	Else
		LOG EVENT:C667(Into 4D debug message:K38:5; $message)
	End if
	
Function get controller()->$controller : cs:C1710._Normal_Controller
	
	$controller:=This:C1470._controller
	
Function _installed($resource : Text; $option : Object) : Collection
	
	Case of 
		: ($resource="backends")
			If (Value type:C1509($option.backends_path)=Is object:K8:27) && (OB Instance of:C1731($option.backends_path; 4D:C1709.Folder))
				$command:=This:C1470.escape(This:C1470.executablePath)
				$command+=" "
				$command+=($resource+" list")
				$command+=" --backends-path="
				$command+=This:C1470.escape(This:C1470.expand($option.backends_path).path)
			Else 
				return 
			End if 
		: ($resource="models")
			If (Value type:C1509($option.models_path)=Is object:K8:27) && (OB Instance of:C1731($option.models_path; 4D:C1709.Folder))
				$command:=This:C1470.escape(This:C1470.executablePath)
				$command+=" "
				$command+=($resource+" list")
				$command+=" --models-path="
				$command+=This:C1470.escape(This:C1470.expand($option.models_path).path)
				If (OB Instance of:C1731($option.backends_path; 4D:C1709.Folder))
					$command+=" --backends-path="
					$command+=This:C1470.escape(This:C1470.expand($option.backends_path).path)
				End if
			Else 
				return 
			End if 
		Else 
			return 
	End case 
	
	$worker:=This:C1470.controller.execute($command; Null:C1517).worker
	$worker.wait()
	$info:=This:C1470.controller.stdOut
	This:C1470.controller.clear()
	
	var $resources : Collection
	$resources:=[]
	
	ARRAY LONGINT:C221($pos; 0)
	ARRAY LONGINT:C221($len; 0)
	var $line : Text
	For each ($line; Split string:C1554($info; This:C1470.EOL))
		Case of 
			: (Match regex:C1019("^ \\* ([^\\s]+)(?:\\s+v[^\\s]+)?\\s+\\(installed(?:, [^)]*)?\\)"; $line; 1; $pos; $len))
				$resources.push(Substring:C12($line; $pos{1}; $len{1}))
		End case 
	End for each 
	
	return $resources
	
Function _simple($params : Object; $option : Variant; $formula : 4D:C1709.Function) : Collection
	
	$installed_backends:=This:C1470._installed("backends"; $params)
	$installed_models:=This:C1470._installed("models"; $params)
	
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
		
		var $installed : Boolean
		Case of 
			: ($option.resource="backends")
				$installed:=$installed_backends.includes($option.name)
			: ($option.resource="models")
				$installed:=$installed_models.includes($option.name)
			Else 
				$installed:=False:C215
		End case 
		
		If ($installed)
			If (OB Instance of:C1731(This:C1470.onSuccess; 4D:C1709.Function))
				var $model : cs:C1710.event.model
				$model:=cs:C1710.event.model.new($option.name; True:C214)
				var $models : cs:C1710.event.models
				$models:=cs:C1710.event.models.new([$model])
				This:C1470.onSuccess.call(This:C1470; Null:C1517; $models)
			End if 
			continue
		End if 
		
		$stdOut:=Not:C34(OB Instance of:C1731($option.output; 4D:C1709.File))
		
		$command:=This:C1470.escape(This:C1470.executablePath)
		$command+=" "
		$command+=($option.resource+" install")
		
		If (Value type:C1509($option.name)=Is text:K8:3) && ($option.name#"")
			$command+=" "
			$command+=This:C1470.escape($option.name)
		Else 
			continue  //mandatory
		End if 
		
		Case of 
			: ($option.resource="backends")
				If (Value type:C1509($option.backends_path)=Is object:K8:27) && (OB Instance of:C1731($option.backends_path; 4D:C1709.Folder))
					$command+=" --backends-path="
					$command+=This:C1470.escape(This:C1470.expand($option.backends_path).path)
				Else 
					continue  //mandatory
				End if 
			: ($option.resource="models")
				If (Value type:C1509($option.models_path)=Is object:K8:27) && (OB Instance of:C1731($option.models_path; 4D:C1709.Folder))
					$command+=" --models-path="
					$command+=This:C1470.escape(This:C1470.expand($option.models_path).path)
					$command+=" --backends-path="
					$command+=This:C1470.escape(This:C1470.expand($params.backends_path).path)
				Else 
					continue  //mandatory
				End if 
		End case 
		
		var $arg : Object
		var $valueType : Integer
		var $key : Text
		
		For each ($arg; OB Entries:C1720($option))
			Case of 
				: (["resource"; "name"; "models_path"; "backends_path"].includes($arg.key))
					continue
			End case 
			$valueType:=Value type:C1509($arg.value)
			$key:=Replace string:C233($arg.key; "_"; "-"; *)
			Case of 
				: ($valueType=Is real:K8:4)
					$command+=(" --"+$key+"="+_argNumber($arg.value)+" ")
				: ($valueType=Is integer:K8:5)
					$command+=(" --"+$key+"="+String:C10($arg.value)+" ")
				: ($valueType=Is text:K8:3)
					$command+=(" --"+$key+"="+This:C1470.escape($arg.value)+" ")
				: ($valueType=Is boolean:K8:9)
					$command+=(" --"+$key+"="+($arg.value ? "true" : "false")+" ")
				Else 
					//
			End case 
		End for each 
		
		//SET TEXT TO PASTEBOARD($command)
		
		var $worker : 4D:C1709.SystemWorker
		$worker:=This:C1470.controller.execute($command; Null:C1517; $option.name).worker
		
		If (Not:C34($isAsync))
			$worker.wait()
			If ($worker.exitCode#0)
				This:C1470.installFailed:=True:C214
				This:C1470._error($option; $worker.exitCode; This:C1470.controller.stdErr)
				break
			End if
			If (OB Instance of:C1731(This:C1470.onSuccess; 4D:C1709.Function))
				This:C1470.onSuccess.call(This:C1470; $worker; cs:C1710.event.models.new([cs:C1710.event.model.new($option.name; True:C214)]))
			End if
		End if 
		
		If ($stdOut) && (Not:C34($isAsync))
			$results.push(This:C1470.controller.stdOut)
			This:C1470.controller.clear()
		End if 
		
	End for each 
	
	If ($stdOut) && (Not:C34($isAsync))
		return $results
	End if 
	
Function install($params : Object; $option : Variant; $formula : 4D:C1709.Function) : Collection
	
	This:C1470.bind($params; ["onSuccess"; "onData"; "onError"])
	This:C1470.installFailed:=False:C215
	
	var $models; $backends : Collection
	$models:=$option.models.map(Formula:C1597($1.result:={resource: "models"; name: $1.value; models_path: $2}); $option.options.models_path)
	$backends:=$option.backends.map(Formula:C1597($1.result:={resource: "backends"; name: $1.value; backends_path: $2}); $option.options.backends_path)
	
	return This:C1470._simple($option.options; $backends.combine($models); $formula)