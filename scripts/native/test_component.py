"""Static 4D integration regressions; these do not compile or execute 4D code."""

import json
from pathlib import Path
import re
import shlex
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "LocalAI"
SOURCES = COMPONENT / "Project" / "Sources"
STRING_LITERAL = r'"(?:[^"\\]|\\.)*"'


def source(relative):
    return (SOURCES / relative).read_text(encoding="utf-8")


def function(text, name):
    match = re.search(
        rf"^Function {re.escape(name)}(?:\(|\s).*?(?=^Function |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Missing function {name}")
    return match.group()


class ComponentStaticTests(unittest.TestCase):
    def test_project_metadata_parses(self):
        for path in COMPONENT.rglob("*.json"):
            with self.subTest(path=path):
                json.loads(path.read_text(encoding="utf-8"))
        json.loads((COMPONENT / "Project/LocalAI.4DProject").read_text())
        ET.parse(SOURCES / "settings.4DSettings")

    def test_control_blocks_balance(self):
        blocks = {
            "If": "End if",
            "Case of": "End case",
            "While": "End while",
            "For each": "End for each",
            "For": "End for",
        }
        for path in SOURCES.rglob("*.4dm"):
            stack = []
            text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.DOTALL)
            for number, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                for opening, closing in blocks.items():
                    if stripped == opening or stripped.startswith(opening + " ("):
                        stack.append(closing)
                        break
                if stripped in blocks.values():
                    with self.subTest(path=path, line=number):
                        self.assertTrue(stack, "Closing block without an opening")
                        self.assertEqual(stack.pop(), stripped)
            self.assertEqual(stack, [], str(path))

    def test_legacy_platform_selection_is_not_a_release_matrix_gate(self):
        public = source("Classes/LocalAI.4dm")
        server = source("Classes/_server.4dm")
        self.assertNotIn("Is Windows:C1573", public)
        self.assertNotIn("Is Windows:C1573", server)
        self.assertNotIn("requires macOS arm64", public)
        selection = source("Classes/_LocalAI.4dm")
        self.assertIn(
            '(Is macOS:C1572) && (Get system info:C1571.processor#"@Apple@")',
            selection,
        )
        self.assertRegex(
            selection,
            r'\$program:="local-ai-x86_64"\s+Else\s+\$program:="local-ai"',
        )
        self.assertIn("Super:C1705($program; $controller)", selection)
        cli = source("Classes/_CLI.4dm")
        self.assertIn('This:C1470._executableName:=$executableName+".exe"', cli)
        self.assertIn("This:C1470._executableFile.exists", cli)
        self.assertIn("This:C1470._executablePath:=This:C1470.executableName", cli)

    def test_managed_worker_reuse_precedes_launch_preparation(self):
        public = source("Classes/LocalAI.4dm")
        normalize = public.index("If ($port<=0)")
        reuse = public.index("If (Not:C34($LocalAI.isRunning($port)))")
        storage = public.index("$HOME.create()")
        schedule = public.index("This:C1470._main(")
        self.assertLess(normalize, reuse)
        self.assertLess(reuse, storage)
        self.assertLess(storage, schedule)
        self.assertIn(
            "$HOME; This:C1470.options; $event)", public
        )

    def test_default_paths_and_flags_remain_legacy_compatible(self):
        public = source("Classes/LocalAI.4dm")
        self.assertIn('This:C1470.options.host:="127.0.0.1"', public)
        self.assertIn("$port:=8080", public)
        for path in ("models", "backends"):
            self.assertIn(f'$HOME.folder("{path}")', public)
        self.assertIn('$backends:=["localai@metal-llama-cpp"]', public)
        self.assertIn('$backends:=["localai@cpu-llama-cpp"]', public)
        self.assertIn(
            '$models:=["localai@nomic-embed-text-v1.5"; '
            '"localai@llama-3.2-1b-instruct:q4_k_m"]',
            public,
        )
        for path in SOURCES.rglob("*.4dm"):
            text = path.read_text()
            self.assertNotIn("disable_local_ai_assistant", text, str(path))
            self.assertNotIn("--disable-local-ai-assistant", text, str(path))

    def test_installation_finishes_before_server_registration(self):
        start = source("Methods/start.4dm")
        self.assertIn("$options; Null:C1517)", start)
        self.assertLess(
            start.index(".install("),
            start.index("If (Not:C34($LocalAI.installFailed))"),
        )
        self.assertLess(
            start.index("If (Not:C34($LocalAI.installFailed))"),
            start.index(".start("),
        )
        simple = function(source("Classes/_server.4dm"), "_simple")
        self.assertLess(simple.index("$worker.wait()"), simple.index("$worker.exitCode#0"))
        self.assertLess(
            simple.index("This:C1470.installFailed:=True:C214"),
            simple.index("break"),
        )
        self.assertIn("This:C1470._error($option; $worker.exitCode;", simple)

    def test_failures_have_callback_or_log_and_shutdown_does_not_start(self):
        server = source("Classes/_server.4dm")
        error = function(server, "_error")
        self.assertIn("This:C1470.onError.call(", error)
        self.assertIn("LOG EVENT:C667(Into 4D debug message:K38:5;", error)
        self.assertIn("LocalAI command failed with exit code", error)
        start = function(server, "start")
        for option in ("models_path", "backends_path", "HOME"):
            self.assertIn(f"LocalAI start requires {option}", start)
        public = source("Classes/LocalAI.4dm")
        self.assertIn("OB Instance of:C1731($options.event.onError;", public)
        self.assertIn("LOG EVENT:C667(Into 4D debug message:K38:5;", public)
        exit_method = source("DatabaseMethods/onExit.4dm")
        self.assertNotIn("LocalAI.new", exit_method)
        self.assertIn(".terminate()", exit_method)

    def test_numeric_boolean_and_metadata_command_invariants(self):
        server = source("Classes/_server.4dm")
        for name in ("start", "_simple"):
            text = function(server, name)
            self.assertIn("($valueType=Is integer:K8:5)", text)
            self.assertIn('($arg.value ? "true" : "false")', text)
        start = function(server, "start")
        metadata = re.search(r"\[(.*?)\]\.includes\(\$arg.key\)", start).group(1)
        for name in ("HOME", "models", "backends", "data", "onError", "onTerminate"):
            self.assertIn(f'"{name}"', metadata)
        self.assertIn('+" run"', start)
        self.assertIn("This:C1470.escape($address)", start)
        simple = function(server, "_simple")
        self.assertIn("This:C1470.expand($params.backends_path).path", simple)
        install = function(server, "install")
        self.assertNotIn("$option.models:=", install)
        self.assertNotIn("$option.backends:=", install)

    def test_queue_metadata_initialization_abort_and_empty_input(self):
        controller = source("Classes/_CLI_Controller.4dm")
        execute = function(controller, "execute")
        for name in ("messages", "contexts"):
            self.assertLess(
                execute.index(f"${name}:=[]"),
                execute.index(f"${name}[$commands.length-1]"),
            )
        self.assertLess(
            execute.index("If ($commands.length=0)"),
            execute.index("$messages[$commands.length-1]"),
        )
        abort = function(controller, "_abort")
        for name in ("commands", "messages", "contexts"):
            self.assertIn(f"This:C1470._{name}.clear()", abort)

    def test_installed_listing_fixtures_use_source_pattern(self):
        server = source("Classes/_server.4dm")
        literal = re.search(rf"Match regex:C1019\(({STRING_LITERAL})", server).group(1)
        pattern = re.compile(json.loads(literal))
        fixtures = [
            (" * localai@cpu-llama-cpp (installed)", "localai@cpu-llama-cpp"),
            (" * localai@cpu-llama-cpp v1.2.3 (installed)", "localai@cpu-llama-cpp"),
            (
                " * localai@cpu-llama-cpp v1.2.3 "
                "(installed, upgrade available: 2.0.0)",
                "localai@cpu-llama-cpp",
            ),
            (
                " * localai@cpu-llama-cpp (installed, upgrade available: new build)",
                "localai@cpu-llama-cpp",
            ),
            (
                " * localai@llama-3.2-1b-instruct:q4_k_m (installed)\r",
                "localai@llama-3.2-1b-instruct:q4_k_m",
            ),
            (" - localai@not-installed v1.0", None),
        ]
        for line, expected in fixtures:
            with self.subTest(line=line):
                match = pattern.search(line)
                self.assertEqual(match.group(1) if match else None, expected)

    def test_posix_quoting_fixtures_use_source_literals(self):
        escape = function(source("Classes/_CLI.4dm"), "escape")
        mac = escape.split(": (Is macOS:C1572)", 1)[1]
        literal = f"({STRING_LITERAL})"
        expression = re.search(
            rf"\$out:={literal}\+Replace string:C233"
            rf"\(\$in; {literal}; {literal}; \*\)\+{literal}",
            mac,
        )
        self.assertIsNotNone(expression)
        prefix, needle, replacement, suffix = map(json.loads, expression.groups())
        fixtures = [
            "",
            "normal",
            "/Users/A name/models",
            "O'Brien",
            "line\nnext\tpart",
            "$(touch do-not-run); `echo unsafe`",
            "trailing\\",
        ]
        for value in fixtures:
            with self.subTest(value=value):
                quoted = prefix + value.replace(needle, replacement) + suffix
                self.assertEqual(shlex.split(quoted), [value])

    def test_windows_escaping_keeps_original_non_posix_branch(self):
        escape = function(source("Classes/_CLI.4dm"), "escape")
        windows = escape.split(": (Is Windows:C1573)", 1)[1].split(
            ": (Is macOS:C1572)", 1
        )[0]
        self.assertIn(r'$metacharacters:="&|<>()%^\" "', windows)
        self.assertIn(r'If (Substring:C12($out; Length:C16($out))="\\")', windows)
        self.assertIn(r'$out:="\""+$out+"\\\""', windows)
        self.assertIn(r'$out:="\""+$out+"\""', windows)
        self.assertNotIn("Replace string:C233", windows)
        self.assertNotIn("shlex", windows)

    def test_modern_only_documentation_requires_replacement(self):
        guide = (COMPONENT / "Documentation/Classes/_LocalAI.md").read_text()
        self.assertIn("validated source-built macOS arm64", guide)
        self.assertIn("LocalAI/Resources/bin/macOS/local-ai", guide)
        self.assertIn("best-effort legacy operation", guide)
        self.assertIn(
            "exact LocalAI versions of all three checked-in executables are unknown",
            guide,
        )
        self.assertIn("Mach-O arm64 executable", guide)
        self.assertIn("require\n   nonempty version/commit output", guide)
        self.assertIn(
            "resolver does not inspect executable versions or architectures", guide
        )
        example = re.search(r"```4d\n(.*?)```", guide, re.DOTALL).group(1)
        self.assertNotIn("disable_local_ai_assistant", example)
        self.assertNotIn("disable-local-ai-assistant", example)
        self.assertNotIn("legacy_executable", source("Classes/LocalAI.4dm"))


if __name__ == "__main__":
    unittest.main()
