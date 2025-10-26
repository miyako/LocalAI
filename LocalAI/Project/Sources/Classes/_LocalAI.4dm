Class extends _CLI

Class constructor($controller : 4D:C1709.Class)
	
	If (Not:C34(OB Instance of:C1731($controller; cs:C1710._LocalAI_Controller)))
		$controller:=cs:C1710._LocalAI_Controller
	End if 
	
	var $program : Text
	Case of 
		: (Is macOS:C1572) && (Get system info:C1571.macRosetta)
			$program:="local-ai-x86_64"
		Else 
			$program:="local-ai"
	End case 
	
	Super:C1705($program; $controller)
	
Function get worker() : 4D:C1709.SystemWorker
	
	return This:C1470.controller.worker
	
Function terminate()
	
	This:C1470.controller.terminate()