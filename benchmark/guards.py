"""Safety guards for unattended benchmark runs.

The benchmark runs the agent 30 times with nobody watching, so the risky tools
are patched in place before the first app.invoke(). The graph and the ToolNode
share the same tool objects, so replacing `tool.func` covers both. Each tool's
name, description and argument schema stay the same, so the model sees the
same tools as in normal use.

- run_command: refuses commands matching BLOCKED_PATTERN and write commands
  (mkdir, cp, mv, tee, >, ...) aimed outside the sandbox. Everything else runs
  inside the run's sandbox with a timeout, and the whole process group is
  killed if it hangs.
- write_file, create_project_folder: refuse paths outside the sandbox.
- SKIPPED: tools no task needs that change the system or open windows become
  no-ops. The harness also answers "no" to every confirmation, so the
  dangerous tools never reach this layer in practice.

This is a safety net, not a jail: read-only tools still see the whole disk,
and a determined shell command can still write outside the sandbox. Every
refusal is recorded, so a run that tries it shows up in the results.
"""

import logging
import os
import pathlib
import re
import signal
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

COMMAND_TIMEOUT = 60  # seconds per run_command call
BLOCKED_PATTERN = re.compile(
    r"\b(sudo|su|apt|apt-get|dpkg|snap|pip3?\s+install|rm|shred|truncate|mkfs|dd"
    r"|shutdown|reboot|systemctl|kill|pkill|killall|chown)\b"
    r"|\s-delete\b"
)
# Shell writes: only the command head counts (heredoc bodies and quoted strings
# are data, e.g. "/api/calculate" inside app code), and URLs are not paths.
WRITE_MARKER = re.compile(r"\b(mkdir|touch|cp|mv|tee|ln|chmod|sed\s+-i)\b|>")
PATH_TOKEN = re.compile(r"(?<![\w.:/-])(~|/)[^\s;|&<>]*")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
SANDBOXED = {"write_file", "create_project_folder"}
SKIPPED = {
    "install_package",
    "remove_package",
    "remove_file",
    "empty_trash",
    "clear_tmp",
    "kill_process",
    "run_deploy_script",
    "stop_frontend",
    "open_vscode",
    "open_browser",
    "open_file",
    "enable_wifi",
    "duckduckgo_search_images",  # downloads into ~/media
}

BLOCKED_COMMANDS = []  # tool calls the guard refused (commands, writes outside the sandbox)
SKIPPED_TOOLS = []  # no-op'd tools the agent still called

_sandbox: Optional[pathlib.Path] = None
_installed = False


# --------------------------------------------------------------------------- #
# Guarded tool functions
# --------------------------------------------------------------------------- #
def _refuse(record: str, reason: str) -> str:
    BLOCKED_COMMANDS.append(record)
    logger.warning(f"[GUARD] Blocked {record}")
    return f"Error: blocked by benchmark harness ({reason})"


def _inside_sandbox(path: str) -> bool:
    if _sandbox is None:
        return False
    target = os.path.abspath(os.path.expanduser(path))
    return os.path.commonpath([target, str(_sandbox)]) == str(_sandbox)


def _write_outside_sandbox(command: str) -> Optional[str]:
    """Return the first path outside the sandbox that a write-like command touches."""
    head = QUOTED.sub("", command.split("<<", 1)[0])
    if not WRITE_MARKER.search(head):
        return None
    if _sandbox is None:
        return "(no sandbox during warm-up)"
    for match in PATH_TOKEN.finditer(head):
        path = match.group(0)
        if not path.startswith("/dev/") and not _inside_sandbox(path):
            return path
    return None


def guarded_run_command(command: str) -> str:
    """Run a shell command and return the output."""
    if BLOCKED_PATTERN.search(command):
        return _refuse(f"run_command: {command}", "command not allowed during the benchmark")
    outside = _write_outside_sandbox(command)
    if outside:
        return _refuse(f"run_command: {command}", f"writes outside the sandbox: {outside}")

    process = subprocess.Popen(
        command,
        shell=True,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        executable="/bin/bash",
        cwd=_sandbox,
        start_new_session=True,  # own process group, so a timeout kills its children too
    )
    try:
        stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        logger.warning(f"[GUARD] run_command timed out after {COMMAND_TIMEOUT}s: {command}")
        return f"Error: command timed out after {COMMAND_TIMEOUT}s"

    # Same output contract as tools_module/runCommand.py
    if process.returncode != 0:
        return f"Error: {stderr}"
    return stdout


def _guard_write_file(original):
    def guarded_write_file(working_directory: str, file_path: str, content: str) -> str:
        target = os.path.join(os.path.expanduser(working_directory), file_path)
        if not _inside_sandbox(target):
            return _refuse(f"write_file: {os.path.abspath(target)}", "path is outside the sandbox")
        return original(working_directory, file_path, content)

    return guarded_write_file


def _guard_create_project_folder(original):
    def guarded_create_project_folder(working_directory: str, project_name: str) -> str:
        target = os.path.join(os.path.expanduser(working_directory), project_name)
        if not _inside_sandbox(target):
            return _refuse(
                f"create_project_folder: {os.path.abspath(target)}", "path is outside the sandbox"
            )
        return original(working_directory, project_name)

    return guarded_create_project_folder


def _skip(name: str):
    def skipped(*args, **kwargs) -> str:
        SKIPPED_TOOLS.append(name)
        logger.info(f"[GUARD] Skipped {name}")
        return f"Skipped: {name} is disabled during the benchmark."

    return skipped


# --------------------------------------------------------------------------- #
# Install
# --------------------------------------------------------------------------- #
def install(sandbox: Optional[pathlib.Path] = None) -> None:
    """Patch the agent's tools. Call once, before the first app.invoke().

    `sandbox` is the only folder writes are allowed in, and the working
    directory for run_command. Without one (warm-up), every write is refused.
    """
    global _sandbox, _installed
    if _installed:
        return
    from core.tools import __all__ as tool_functions

    _sandbox = pathlib.Path(sandbox).resolve() if sandbox else None
    tools = {tool.name: tool for tool in tool_functions}

    # Fail loudly if a tool was renamed: an unguarded tool must never slip through
    missing = (SKIPPED | SANDBOXED | {"run_command"}) - tools.keys()
    if missing:
        raise RuntimeError(f"guards: tools not found, update guards.py: {sorted(missing)}")

    tools["run_command"].func = guarded_run_command
    tools["write_file"].func = _guard_write_file(tools["write_file"].func)
    tools["create_project_folder"].func = _guard_create_project_folder(
        tools["create_project_folder"].func
    )
    for name in SKIPPED:
        tools[name].func = _skip(name)

    _installed = True
    logger.info(f"[GUARD] Installed (sandbox: {_sandbox})")
