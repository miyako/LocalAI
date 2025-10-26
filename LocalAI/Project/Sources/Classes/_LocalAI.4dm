Class extends _CLI

Class constructor($command : Text; $controller : 4D:C1709.Class)
	
	If (Not:C34(OB Instance of:C1731($controller; cs:C1710._LocalAI_Controller)))
		$controller:=cs:C1710._LocalAI_Controller
	End if 
	
	var $program : Text
	$program:="local-ai"
	
	Super:C1705($program; $controller)
	
Function get worker() : 4D:C1709.SystemWorker
	
	return This:C1470.controller.worker
	
Function terminate()
	
	This:C1470.controller.terminate()