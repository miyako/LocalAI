//%attributes = {"invisible":true}
var $parameter : Text
var $result : Integer
$result:=Get database parameter:C643(User param value:K37:94; $parameter)
var $input; $options; $report : Object
$input:=JSON Parse:C1218($parameter)
var $project : 4D:C1709.File
$project:=File:C1566($input.project; fk posix path:K87:1)
var $builder : cs:C1710.BuildApp
$builder:=cs:C1710.BuildApp.new()
$options:=New object:C1471
$options.generateSymbols:=False:C215
$options.generateSyntaxFile:=True:C214
$options.components:=$builder.findComponents($project; True:C214)
//Declared dependencies (dependencies.json) fetched by component.py, as compiled .4DZ files.
var $path : Text
For each ($path; $input.components)
	$options.components.push(File:C1566($path; fk posix path:K87:1))
End for each 
$options.plugins:=$builder.findPluginsFolder($project)
$options.targets:=New collection:C1472("arm64_macOS_lib"; "x86_64_generic")
$report:=Compile project:C1760($project; $options)
File:C1566($input.report; fk posix path:K87:1).setText(JSON Stringify:C1217($report); "utf-8"; Document with LF:K24:22)
