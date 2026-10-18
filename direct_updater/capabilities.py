"""Bounded, static evidence collection. Findings describe code, never enforced access."""

import ast
import hashlib
import json
import os
import re
import stat
import shlex
from urllib.parse import urlsplit
from functools import lru_cache
from pathlib import Path

SCANNER_VERSION = 6
MAX_FILE = 1024 * 1024
MAX_SCRIPT = 2 * 1024 * 1024
MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_FINDINGS = 128
SOURCE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".bash"}


def _native(data):
    return data.startswith((b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"))


def _call_name(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _call_name(node.value, aliases) + "." + node.attr
    return ""


def _literal(node, values, aliases):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if len(node.value) <= 8192 else None
    if isinstance(node, ast.Name):
        value = values.get(node.id)
        return value if value is not None and len(value) <= 8192 else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        left, right = _literal(node.left, values, aliases), _literal(node.right, values, aliases)
        if left is not None and right is not None and len(left) + len(right) < 8192:
            return (
                left + right
                if isinstance(node.op, ast.Add)
                else left.rstrip("/") + "/" + right.lstrip("/")
            )
    if isinstance(node, ast.Call):
        name = _call_name(node.func, aliases)
        if name in {"pathlib.Path.home", "Path.home"}:
            return "~"
        if name in {"pathlib.Path", "Path", "os.path.join", "os.path.expanduser"}:
            parts = [_literal(arg, values, aliases) for arg in node.args]
            if (
                parts
                and all(part is not None for part in parts)
                and sum(len(part) + 1 for part in parts) <= 8192
            ):
                return "/".join(
                    part.strip("/") if i else part.rstrip("/") for i, part in enumerate(parts)
                )
    return None


def _folder(text, directory=False):
    if not text or len(text) > 256 or any(ord(char) < 32 for char in text) or "://" in text:
        return None
    if not text.startswith(("/", "~/", "./", "../")):
        return None
    text = re.sub(r"^/home/[^/]+(?=/|$)", "~", text)
    return text.rstrip("/") or "/" if directory else str(Path(text).parent)


SHELL_SYNTAX = {
    "if",
    "then",
    "elif",
    "else",
    "fi",
    "for",
    "while",
    "until",
    "do",
    "done",
    "case",
    "esac",
    "in",
    "select",
    "function",
    "break",
    "continue",
    "return",
    "exit",
    "local",
    "declare",
    "typeset",
    "export",
    "readonly",
    "unset",
    "set",
    "shift",
    "shopt",
    "read",
    "echo",
    "printf",
    "true",
    "false",
    "command",
    "builtin",
    "source",
    "eval",
    "exec",
    "test",
    "trap",
    "wait",
    "cd",
    "pwd",
    "let",
    "getopts",
    "umask",
    "ulimit",
    "pushd",
    "popd",
    "dirs",
}


def _device_paths(text):
    pseudo = {
        "/dev/null",
        "/dev/zero",
        "/dev/full",
        "/dev/random",
        "/dev/urandom",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/tty",
        "/dev/console",
        "/dev/ptmx",
        "/dev/fd",
        "/dev/pts",
        "/dev/shm",
    }
    return [
        path
        for path in re.findall(r"/dev/[A-Za-z0-9_./*-]+", text)
        if path.rstrip("/") not in pseudo
        and not path.startswith(("/dev/fd/", "/dev/pts/", "/dev/shm/"))
    ]


def _shell_lines(text):
    # Skip here-document data and join quoted/continued lines before looking for commands.
    heredocs, buffer, start = [], "", 0
    for number, line in enumerate(text.splitlines(), 1):
        if heredocs:
            delimiter, tabs = heredocs[0]
            if (line.lstrip("\t") if tabs else line) == delimiter:
                heredocs.pop(0)
            continue
        if not buffer:
            start = number
        buffer += line + "\n"
        if len(buffer) > 8192:
            # A large or unterminated construct is unknown, not command evidence.
            return
        if line.rstrip().endswith("\\"):
            continue
        try:
            lexer = shlex.shlex(buffer, posix=False, punctuation_chars=";<>&|()")
            lexer.whitespace_split = True
            words = list(lexer)
        except ValueError:
            continue
        for index, token in enumerate(words[:-1]):
            if token == "<<":
                delimiter = words[index + 1]
                tabs = delimiter.startswith("-")
                delimiter = delimiter.lstrip("-") if tabs else delimiter
                delimiter = delimiter.strip("\"'")
                if (
                    delimiter
                    and len(delimiter) <= 80
                    and not any(ord(char) < 32 for char in delimiter)
                ):
                    heredocs.append((delimiter, tabs))
        yield start, buffer
        buffer = ""


def _command_names(command, shell=False):
    try:
        if shell:
            lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&")
            lexer.whitespace_split = True
            words = list(lexer)
        else:
            words = shlex.split(command)
    except ValueError:
        return []
    if not words:
        return []
    names = []
    first = Path(words[0]).name
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.+-]{0,79}", first) and (
        not shell or first not in SHELL_SYNTAX
    ):
        names.append(first)
    if first in {"sudo", "pkexec"} and len(words) > 1 and not words[1].startswith("-"):
        names += _command_names(words[1])
    if shell and first in {"sh", "bash"} and len(words) > 2 and words[1] == "-c":
        names += _command_names(words[2])
    if shell:
        for index, word in enumerate(words[:-1]):
            if word in {"|", "||", "&&", ";", "&"}:
                names += _command_names(words[index + 1])
    return list(dict.fromkeys(names))


def _domains(strings):
    hosts = set()
    for text in strings:
        for url in re.findall(r"https?://[^\s'\"<>]+", text):
            try:
                parsed = urlsplit(url)
                host = parsed.hostname
                if host and len(host) <= 253:
                    host = host.encode("idna").decode("ascii").lower().rstrip(".")
                    if re.fullmatch(r"[a-z0-9.:-]+", host):
                        target = host
                        parts = parsed.path.strip("/").split("/")
                        if host in {"github.com", "raw.githubusercontent.com"}:
                            project = parts[:2]
                        elif host == "api.github.com" and parts[0] == "repos":
                            project = parts[:3]
                        else:
                            project = []
                        for part in project:
                            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part) or part in {
                                ".",
                                "..",
                            }:
                                break
                            target += "/" + part
                        hosts.add(target)
            except (ValueError, UnicodeError):
                pass
    return sorted(hosts)[:16]


def _endpoint_hosts(node, values, aliases, depth=0):
    if node is None or depth > 12:
        return []
    literal = _literal(node, values, aliases)
    if literal is not None:
        return _domains([literal])
    if isinstance(node, ast.Name):
        value = values.get(node.id)
        return _domains([value]) if value else []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        prefix = _literal(node.left, values, aliases)
        if prefix is not None and (prefix.endswith((".", "://"))):
            return []
        return _endpoint_hosts(node.left, values, aliases, depth + 1)
    if isinstance(node, ast.JoinedStr):
        prefix = ""
        for part in node.values:
            if not isinstance(part, ast.Constant) or not isinstance(part.value, str):
                break
            prefix += part.value
        # An unknown expression in the hostname cannot establish a destination.
        if re.match(r"https?://[^/]+/", prefix):
            return _domains([prefix])
    if (
        isinstance(node, ast.Call)
        and _call_name(node.func, aliases) == "urllib.request.Request"
        and node.args
    ):
        return _endpoint_hosts(node.args[0], values, aliases, depth + 1)
    return []


def _python(text, emit, native_names):
    tree = ast.parse(text)
    # Bind imports, but only calls (not imports alone) constitute operation evidence.
    aliases, values = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name] = item.name
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                aliases[item.asname or item.name] = (node.module or "") + "." + item.name
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                    values[target.id] = node.value.value
    for node in ast.walk(tree):
        candidates = []
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            candidates = [(target, node.value) for target in node.targets]
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            candidates = [(item.optional_vars, item.context_expr) for item in node.items]
        for target, call in candidates:
            if isinstance(target, ast.Name) and isinstance(call, ast.Call):
                constructor = _call_name(call.func, aliases)
                if constructor in {
                    "aiohttp.ClientSession",
                    "requests.Session",
                    "httpx.Client",
                    "httpx.AsyncClient",
                }:
                    aliases[target.id] = constructor.split(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal(node.value, values, aliases)
            if value is not None:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = value
            else:
                hosts = _endpoint_hosts(node.value, values, aliases)
                if hosts:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            values[target.id] = "https://" + hosts[0] + "/"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func, aliases)
        category = None
        inferred_file_operation = False
        if name.startswith(("requests.", "httpx.", "urllib.request.", "aiohttp.", "socket.")):
            if name.rsplit(".", 1)[-1] in {
                "get",
                "post",
                "put",
                "delete",
                "patch",
                "head",
                "request",
                "urlopen",
                "urlretrieve",
                "socket",
                "create_connection",
                "connect",
                "ClientSession",
                "Request",
            }:
                category = "network"
        elif name in {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "subprocess.check_call",
            "subprocess.check_output",
            "os.system",
            "os.popen",
            "os.execv",
            "os.execve",
            "asyncio.create_subprocess_exec",
            "asyncio.create_subprocess_shell",
        }:
            category = "process_execution"
        elif name in {
            "open",
            "io.open",
            "os.open",
            "os.listdir",
            "os.scandir",
            "os.remove",
            "os.unlink",
        } or name.startswith("shutil."):
            category = "filesystem"
        elif isinstance(node.func, ast.Attribute) and node.func.attr in {
            "read_text",
            "write_text",
            "read_bytes",
            "write_bytes",
            "unlink",
            "mkdir",
            "iterdir",
        }:
            # Receiver types are not resolved; distinguish this from known built-in calls.
            category = "filesystem"
            inferred_file_operation = True
            emit("filesystem", "File operation", node.lineno, "heuristic")
        targets = []
        if category == "filesystem":
            arguments = node.args[:2] if name.startswith("shutil.") else node.args[:1]
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "read_text",
                "write_text",
                "read_bytes",
                "write_bytes",
                "unlink",
                "mkdir",
                "iterdir",
            }:
                arguments = [node.func.value]
            if not arguments:
                arguments = [item.value for item in node.keywords if item.arg in {"file", "path"}]
            for argument in arguments:
                value = _literal(argument, values, aliases)
                folder = _folder(
                    value,
                    directory=name in {"os.listdir", "os.scandir"}
                    or name.endswith((".mkdir", ".iterdir")),
                )
                if folder:
                    targets.append(folder)
                if value and value.startswith("/dev/") and _device_paths(value):
                    emit(
                        "devices",
                        "Device path referenced",
                        node.lineno,
                        "heuristic",
                        targets=_device_paths(value),
                    )
        if category:
            emit(
                category,
                "Code operation",
                node.lineno,
                "heuristic" if inferred_file_operation else "identified",
                targets=targets,
            )
        arguments = list(node.args) + [item.value for item in node.keywords]
        if isinstance(node.func, ast.Attribute):
            arguments.append(node.func.value)
        strings = [
            n.value
            for arg in arguments
            for n in ast.walk(arg)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        strings += [
            values[arg.id] for arg in arguments if isinstance(arg, ast.Name) and arg.id in values
        ]
        if category == "network":
            endpoint = (
                node.args[1]
                if name.endswith(".request") and len(node.args) > 1
                else node.args[0]
                if node.args
                else None
            )
            endpoints = [endpoint] + [item.value for item in node.keywords if item.arg == "url"]
            hosts = sorted(
                {host for value in endpoints for host in _endpoint_hosts(value, values, aliases)}
            )
            if hosts:
                emit("network", "Code operation", node.lineno, "identified", targets=hosts)
        if category in {"filesystem", "process_execution"} or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"read_text", "write_text", "read_bytes", "write_bytes"}
        ):
            _paths(strings, node.lineno, emit)
        if category == "process_execution":
            shell = name in {"os.system", "os.popen", "asyncio.create_subprocess_shell"} or any(
                item.arg == "shell"
                and isinstance(item.value, ast.Constant)
                and item.value.value is True
                for item in node.keywords
            )
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                args = node.args[0].elts
                shell = shell or (
                    len(args) >= 3
                    and isinstance(args[0], ast.Constant)
                    and isinstance(args[0].value, str)
                    and Path(args[0].value).name in {"sh", "bash"}
                    and isinstance(args[1], ast.Constant)
                    and args[1].value == "-c"
                )
            command_node = (
                node.args[0]
                if node.args
                else next((item.value for item in node.keywords if item.arg == "args"), None)
            )
            if isinstance(command_node, (ast.List, ast.Tuple)) and command_node.elts:
                parts = [_literal(arg, values, aliases) for arg in command_node.elts]
                # Only the executable and known wrappers are exposed, never arbitrary arguments.
                command_text = (
                    shlex.join(part for part in parts if part is not None)
                    if parts[0] is not None
                    else ""
                )
            else:
                command_text = _literal(command_node, values, aliases) or ""
            commands = _command_names(command_text, shell=shell)
            if commands:
                emit(
                    "process_execution",
                    "Code operation",
                    node.lineno,
                    "identified",
                    targets=commands,
                )
            if commands and commands[0] in {"sudo", "pkexec"}:
                emit(
                    "root",
                    "Privileged command",
                    node.lineno,
                    "identified",
                    targets=[commands[0]],
                    signal="privileged_execution",
                )
            _command(strings, node.lineno, emit, shell=shell)
            if node.args:
                command = node.args[0]
                if isinstance(command, (ast.List, ast.Tuple)) and command.elts:
                    command = command.elts[0]
                if isinstance(command, ast.Constant) and isinstance(command.value, str):
                    words = shlex.split(command.value)
                    if words and Path(words[0]).name in native_names:
                        emit(
                            "native_binaries",
                            "Native executable invocation",
                            node.lineno,
                            "heuristic",
                        )


def _paths(strings, line, emit):
    for text in strings:
        text = re.sub(r"https?://[^\s'\"<>]+", "", text)
        lower = text.lower()
        if any(
            part in lower
            for part in (
                "/steam/userdata",
                "/steam/config",
                "/steam/steamapps",
                "/steam/appcache",
                "/.steam/",
                "libraryfolders.vdf",
                "localconfig.vdf",
                "loginusers.vdf",
            )
        ):
            emit("steam_data", "Steam path referenced", line, "heuristic")
        paths = _device_paths(text)
        if paths:
            emit("devices", "Device path referenced", line, "heuristic", targets=paths)
        if any(part in text for part in ("/sys/", "/proc/sys/", "/etc/", "/run/systemd/")):
            emit("system_config", "System path referenced", line, "heuristic")


def _command(strings, line, emit, shell=True):
    for text in strings:
        if re.search(r"(?:^|[\s/])(curl|wget)(?:\s|$)", text):
            emit("network", "Code operation", line, "heuristic", targets=_domains(strings))
        if re.search(r"(?:^|[\s/])(sudo|pkexec)(?:\s|$)", text):
            emit("root", "Privileged command", line, "heuristic")
        if re.search(r"(?:^|[\s/])(systemctl|sysctl|powerprofilesctl)(?:\s|$)", text):
            emit("system_config", "System command", line, "heuristic")
        if shell and re.search(r"(?:curl|wget)\b[^\n]*\|\s*(?:sh|bash)\b", text):
            emit("process_execution", "Downloaded code execution", line, "heuristic")
            if re.search(r"http://", text):
                emit(
                    "network",
                    "Code operation",
                    line,
                    "heuristic",
                    targets=_domains([text]),
                    signal="insecure_code_download",
                )


def _script(text, emit, shell=False):
    # Conservative lexical heuristics, explicitly not a JS/TS parser or data-flow analysis.
    patterns = {
        "network": r"\b(?:fetch|fetchNoCors|axios\.(?:get|post)|https?\.request|https?\.get|WebSocket)\s*\(",
        "filesystem": r"\b(?:fs\.)?(?:readFileSync|writeFileSync|readFile|writeFile|readdir|unlink)\s*\(",
        "process_execution": r"(?<![\w$.])(?:child_process\.)?(?:exec|execFile|spawn|execSync)\s*\(",
    }
    url_values = {}
    if not shell:
        for line in text.splitlines():
            if line.lstrip().startswith(("//", "/*", "*")):
                continue
            for match in re.finditer(
                r"\b([A-Za-z_$][\w$]*)\s*=\s*['\"`](https?://[^'\"`\s]+)['\"`]", line
            ):
                if len(match[2]) <= 8192:
                    url_values[match[1]] = match[2]
    functions = (
        set(re.findall(r"(?m)^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\s*\)\s*\{", text))
        if shell
        else set()
    )
    lines = _shell_lines(text) if shell else enumerate(text.splitlines(), 1)
    for number, line in lines:
        if line.lstrip().startswith(("//", "#")):
            continue
        for category, pattern in patterns.items() if not shell else []:
            if re.search(pattern, line):
                targets = []
                literals = []
                for call in re.finditer(pattern, line):
                    value = re.match(r"\s*['\"]([^'\"]+)['\"]", line[call.end() :])
                    if value:
                        literals.append(value[1])
                    if category == "network":
                        argument = line[call.end() :]
                        direct = re.match(r"\s*['\"`](https?://[^'\"`\s]+)", argument)
                        variable = re.match(r"\s*([A-Za-z_$][\w$]*)", argument)
                        template = re.match(r"\s*`\$\{([A-Za-z_$][\w$]*)\}", argument)
                        endpoint = (
                            direct[1]
                            if direct
                            else url_values.get((variable or template)[1], "")
                            if variable or template
                            else ""
                        )
                        targets += _domains([endpoint])
                if category == "filesystem":
                    targets = [folder for value in literals if (folder := _folder(value))]
                elif category == "process_execution":
                    targets = [command for value in literals for command in _command_names(value)]
                emit(category, "Code operation", number, "heuristic", targets=targets)
                _paths([line], number, emit)
                if category == "process_execution":
                    _command([line], number, emit)
        if shell:
            # Only simple command-position words are reported. Complex shell grammar stays unknown.
            match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_+.-]*|[./][A-Za-z0-9_./+-]+)(?=\s|$)", line)
            commands = [
                name
                for name in _command_names(line, shell=False)[:1]
                if match and name not in SHELL_SYNTAX and name not in functions
            ]
            if commands:
                emit("process_execution", "Code operation", number, "heuristic", targets=commands)
                if any(command in {"curl", "wget"} for command in commands):
                    emit("network", "Code operation", number, "heuristic", targets=_domains([line]))
                if commands[0] in {"sudo", "pkexec"}:
                    emit(
                        "root",
                        "Privileged command",
                        number,
                        "identified",
                        targets=[commands[0]],
                        signal="privileged_execution",
                    )
                _paths([line], number, emit)
                _command([line], number, emit)
            elif {"sh", "bash"}.intersection(_command_names(line, shell=True)):
                # Retain download-to-shell review even in a conditional/pipeline.
                _command([line], number, emit)


@lru_cache(maxsize=8)
def _analyze(files, limitations):
    findings = []
    limitations = set(limitations)
    native_paths = {name for name, data in files if _native(data)}
    native_names = {Path(path).name for path in native_paths}
    for name, data in files:

        def emit(
            category,
            description,
            line=None,
            confidence="identified",
            origin="source",
            targets=None,
            signal=None,
        ):
            item = {
                "category": category,
                "description": description,
                "file": name,
                "line": line,
                "confidence": confidence,
                "origin": origin,
                "targets": sorted(set(targets or []))[:16],
                "signal": signal or "downloaded_code_execution"
                if description == "Downloaded code execution"
                else signal,
            }
            if item not in findings and len(findings) < MAX_FINDINGS:
                findings.append(item)
            elif len(findings) >= MAX_FINDINGS:
                limitations.add("Analysis limit reached")

        if name in native_paths:
            emit("native_binaries", "Bundled native binary", origin="binary")
            limitations.add("Binary behavior not analyzed")
            continue
        suffix = Path(name).suffix.lower()
        if data.startswith(b"#!"):
            interpreter = data.split(b"\n", 1)[0][:160]
            if b"python" in interpreter:
                suffix = ".py"
            elif b"sh" in interpreter:
                suffix = ".sh"
        if suffix not in SOURCE_SUFFIXES:
            if data.startswith(b"#!") or suffix in {".pyc", ".pyo", ".zip", ".whl", ".asar"}:
                limitations.add("Some files could not be analyzed")
            continue
        try:
            text = data.decode("utf-8")
            if suffix == ".py":
                _python(text, emit, native_names)
            else:
                _script(text, emit, shell=suffix in {".sh", ".bash"})
                limitations.add("Script analysis is heuristic")
            if suffix != ".py":
                for number, line in enumerate(text.splitlines(), 1):
                    calls = re.findall(r"(?:spawn|execFile|exec)\s*\(\s*['\"]([^'\"]+)['\"]", line)
                    if (
                        suffix in {".sh", ".bash"}
                        and line.strip()
                        and not line.lstrip().startswith("#")
                    ):
                        calls += shlex.split(line)[:1]
                    if any(Path(call).name in native_names for call in calls):
                        emit("native_binaries", "Native executable invocation", number, "heuristic")
        except (SyntaxError, UnicodeError, RecursionError, MemoryError, ValueError):
            limitations.add("Some files could not be analyzed")
    digest = hashlib.sha256()
    for name, data in files:
        if (
            Path(name).suffix.lower() not in SOURCE_SUFFIXES
            and name not in {"plugin.json", "package.json"}
            and not _native(data)
        ):
            continue
        digest.update(name.encode() + b"\0" + hashlib.sha256(data).digest())
    return {
        "scanner_version": SCANNER_VERSION,
        "evidence_hash": digest.hexdigest(),
        "findings": findings,
        "limitations": sorted(limitations),
        "complete": not bool(limitations),
    }


def scan_files(entries):
    """Entries are validated relative names, sizes and bounded readers; never execute them."""
    files, limitations, total = [], set(), 0
    try:
        for index, (name, size, read) in enumerate(entries):
            if index >= MAX_ENTRIES or total >= MAX_BYTES:
                limitations.add("Analysis limit reached")
                break
            # All files receive a magic-header check, including extensionless binaries.
            suffix = Path(name).suffix.lower()
            maximum = MAX_SCRIPT if suffix in {".js", ".ts", ".tsx", ".jsx"} else MAX_FILE
            limit = maximum if suffix in SOURCE_SUFFIXES or size <= maximum else 4
            if size > maximum and limit > 4:
                limitations.add("Analysis limit reached")
                continue
            if size > limit:
                limitations.add("Some files could not be analyzed")
            amount = min(limit, MAX_BYTES - total)
            if size > amount:
                limitations.add("Some files could not be analyzed")
            data = read(amount)
            if len(data) < min(size, amount):
                limitations.add("Some files could not be analyzed")
            total += len(data)
            files.append((name, data))
    except (OSError, ValueError, RuntimeError):
        limitations.add("Some files could not be analyzed")
    return json.loads(json.dumps(_analyze(tuple(sorted(files)), tuple(sorted(limitations)))))


def scan_archive(archive, root):
    def read(entry, limit):
        with archive.open(entry) as stream:
            return stream.read(limit)

    return scan_files(
        (
            entry.filename[len(root) + 1 :],
            entry.file_size,
            lambda limit, entry=entry: read(entry, limit),
        )
        for entry in archive.infolist()
        if not entry.is_dir()
    )


def scan_installed(folder):
    """Never follow installed symlinks, including directory links."""

    def entries():
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Uninspectable folder")
        pending, count = [folder], 0
        while pending:
            base = pending.pop()
            children = []
            with os.scandir(base) as iterator:
                for child in iterator:
                    count += 1
                    if count > MAX_ENTRIES:
                        raise ValueError("Too many entries")
                    children.append(child)
            for child in sorted(children, key=lambda item: item.name):
                path = Path(child.path)
                if child.is_symlink():
                    raise ValueError("Uninspectable link")
                if child.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif child.is_file(follow_symlinks=False):
                    yield (
                        path.relative_to(folder).as_posix(),
                        child.stat(follow_symlinks=False).st_size,
                        lambda limit, path=path: _read_installed(
                            folder, path.relative_to(folder).parts, limit
                        ),
                    )
                else:
                    raise ValueError("Uninspectable file")

    return scan_files(entries())


def _read_installed(folder, parts, limit):
    # Open each path component relative to a pinned directory, never through symlinks.
    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Not a regular file")
            return stream.read(limit)
    finally:
        os.close(descriptor)


def with_manifest(analysis, facts):
    result = json.loads(json.dumps(analysis))
    if facts["root_requested"]:
        result["findings"].insert(
            0,
            {
                "category": "root",
                "description": "Administrator access requested",
                "file": "plugin.json",
                "line": None,
                "confidence": "declared",
                "origin": "manifest",
            },
        )
    if facts["external_binaries"]:
        result["findings"].append(
            {
                "category": "native_binaries",
                "description": "Additional executable downloads declared",
                "file": "package.json",
                "line": None,
                "confidence": "declared",
                "origin": "manifest",
            }
        )
    return result


def compare_capabilities(current, previous, updating):
    categories = sorted({f["category"] for f in current["findings"]}) if current else []
    known = bool(previous and previous.get("scanner_version") == SCANNER_VERSION)
    old = {f["category"] for f in previous["findings"]} if known else set()
    # Source operations are partial evidence; absence never proves lack of access.
    return {
        "baseline_known": known,
        "added": [c for c in categories if c not in old] if known and updating else [],
        "status": "unknown"
        if updating and not known
        else "incomplete"
        if not current or not current["complete"] or (updating and not previous["complete"])
        else "changed"
        if updating and set(categories) - old
        else "no_new_detected",
    }
