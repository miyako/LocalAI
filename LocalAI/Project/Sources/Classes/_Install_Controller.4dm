property stdOut : Text
property stdErr : Text

Class extends _Normal_Controller

Class constructor($CLI : cs:C1710._CLI)
	
	Super:C1705($CLI)
	
	This:C1470.clear()
	
Function onData($worker : 4D:C1709.SystemWorker; $params : Object)
	
	Super:C1706.onData($worker; $params)
	
	var $instance : cs:C1710._server
	$instance:=This:C1470.instance
	
	If ($instance.onData#Null:C1517) && (OB Instance of:C1731($instance.onData; 4D:C1709.Function))
		
		var $stdOut : Text
		$stdOut:=This:C1470.stdOut
		
		ARRAY LONGINT:C221($pos; 0)
		ARRAY LONGINT:C221($len; 0)
		$i:=1
		While (Match regex:C1019("downloading\\s(backend|model)\\s(.+?)\\s+(\\d+)%"; $stdOut; $i; $pos; $len))
			$kind:=Substring:C12($stdOut; $pos{1}; $len{1})
			$fileName:=Substring:C12($stdOut; $pos{2}; $len{2})
			$percentage:=Num:C11(Substring:C12($stdOut; $pos{3}; $len{3}))
			$i:=$pos{0}+$len{0}
			If ($instance.onData#Null:C1517) && (OB Instance of:C1731($instance.onData; 4D:C1709.Function))
				$context:={}
				$context.kind:=$kind
				$context.fileName:=$fileName
				$context.percentage:=$percentage
				$instance.onData.call(This:C1470; $worker; $context)
			End if 
		End while 
		This:C1470.stdOut:=Substring:C12($stdOut; $i)
	End if 
	
Function onDataError($worker : 4D:C1709.SystemWorker; $params : Object)
	
	Super:C1706.onDataError($worker; $params)