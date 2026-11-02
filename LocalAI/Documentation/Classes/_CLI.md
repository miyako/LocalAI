# _CLI

`_CLI` is the base class to implement console program proxies. Extend this class to implement a specific command line interface.

## .new() 

**.new**($executableName : Text) : cs._CLI

Pass the name of the CLI agent and, optionally, a controller class. The generic
resolver checks the following historical resource layout:

```
/RESOURCES/bin/{macOS|Windows}/
```

For the LocalAI v4.12.1 server, see [native installation and platform limits](_LocalAI.md).
The generic Windows `.exe` resolution is not evidence of native LocalAI Windows support.
If the resource executable is absent, resolution falls back to the executable name
on the 4D process's `PATH` (which can differ from an interactive terminal's `PATH`).

The constructor defines the following properties:

|Property|Type|Description|
|:-|:-|:-|
|controller|cs._CLI_Controller|read-only|
|currentDirectory|4D.Folder|read-only|
|EOL|Text|read-only|
|executableFile|4D.File|read-only|
|executableName|Text|read-only|
|executablePath|Text|read-only|
|name|Text|read-only|
|platform|Text|read-only|

The class is intended to be subclassed. `.name` returns the value `OB Class(This).name` which is the name of the extended class, not this class.

## .escape()

**.escape()**($in : Text) : Text

On macOS, return one POSIX single-quoted argument, escaping embedded single quotes.
This preserves empty arguments, spaces, tabs, newlines and shell metacharacters.
On Windows, the legacy helper adds double quotes to strings containing
metacharacters and escapes a trailing backslash; it is not a general Windows
argument encoder. Its historical behavior is retained for best-effort execution
of legacy Windows resources; this does not add native Windows v4.12.1 support.

## .quote()

**.quote**($in : Text) : Text

Simply add double quotes on each sides of a string. Some CLI agent prefer this type of escaping.

## ._chmod()

**._chmod()**

Executable files transferred from server to client in `/RESOURCES/` are copies as regular documents and missing the UNIX executable bit. This internal function is internally called once in the constructor to make sure that the CLI agent is ready to run on a Mac client.  
