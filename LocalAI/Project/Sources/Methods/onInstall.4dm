//%attributes = {"invisible":true}
#DECLARE($worker : 4D:C1709.SystemWorker; $params : Object)

//var $text : Text
//$text:=$worker.response

If ($params.type="response") && ($params.context#Null:C1517)
	ALERT:C41($params.context)
End if 