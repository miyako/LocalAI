//%attributes = {"invisible":true,"preemptive":"capable"}
#DECLARE($options : Object)

//cs.workers.worker.new(cs._server).start($options.options.port; $options.options)

var $LocalAI : cs:C1710._server
$LocalAI:=cs:C1710._server.new(cs:C1710._Install_Controller)

$lines:=$LocalAI.install($options.event; $options; Formula:C1597(onModel))