property port : Integer
property onData : 4D:C1709.Function
property onDataError : 4D:C1709.Function
property onTerminate : 4D:C1709.Function
property onSuccess : 4D:C1709.Function
property onError : 4D:C1709.Function

Class extends _CLI

Class constructor($class : 4D:C1709.Class)
	
	var $controller : 4D:C1709.Class
	var $superclass : 4D:C1709.Class
	If ($class#Null:C1517)
		$superclass:=$class.superclass
	End if
	$controller:=cs:C1710._LocalAI_Controller
	
	While ($superclass#Null:C1517)
		If ($superclass.name=$controller.name)
			$controller:=$class
			break
		End if 
		$superclass:=$superclass.superclass
	End while 
	
	var $program : Text
	Case of
		: (Is macOS:C1572) && (Get system info:C1571.processor#"@Apple@")
			$program:="local-ai-x86_64"
		Else
			$program:="local-ai"
	End case

	Super:C1705($program; $controller)
	
Function bind($option : Object; $properties : Collection) : cs:C1710._CLI
	
	var $property : Text
	If ($option=Null:C1517)
		return This:C1470
	End if
	For each ($property; $properties)
		This:C1470[$property]:=$option[$property]
	End for each 
	
	return This:C1470
	
Function get worker() : 4D:C1709.SystemWorker
	
	return This:C1470.controller.worker
	
Function terminate()
	
	This:C1470.controller.terminate()