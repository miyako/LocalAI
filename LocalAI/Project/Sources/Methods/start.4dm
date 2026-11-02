//%attributes = {"invisible":true,"preemptive":"capable"}
#DECLARE($options : Object)

var $LocalAI : cs:C1710._server
$LocalAI:=cs:C1710._server.new(cs:C1710._Install_Controller)

$lines:=$LocalAI.install($options.event; $options; Null:C1517)

If (Not:C34($LocalAI.installFailed))
	cs:C1710.workers.worker.new(cs:C1710._server).start($options.options.port; $options.options)
End if