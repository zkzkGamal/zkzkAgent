from langchain_core.tools import tool
import glob, logging, os, shlex, signal, subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COMMAND_TIMEOUT = 60  # seconds; kills the whole process group

# Read-only commands (plus mkdir) run without asking. Everything else goes
# through the confirmation gate in agent_nodes/execute_node.py. An allow-list,
# because a block-list always misses something (python3 -c "os.system(...)").
SAFE_COMMANDS = frozenset({
    "ls", "pwd", "cat", "head", "tail", "wc", "grep", "find", "which", "uname", "df",
    "free", "whoami", "date", "echo", "mkdir", "stat", "du", "file", "hostname",
})
# Chaining, pipes, redirects and substitutions can turn a safe command into anything
SHELL_OPERATORS = (";", "&", "|", ">", "<", "`", "$(", "\n")
# Variable, brace and arithmetic expansion can turn a safe-looking word into an option
EXPANSIONS = ("$", "{", "}")
GLOB_CHARS = "*?["
# find's read-only options and tests; anything else (-delete, -exec, -fprint…) asks first
FIND_READ_ONLY = frozenset({
    "-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
    "-lname", "-ilname", "-type", "-xtype", "-size", "-empty", "-perm", "-user", "-group",
    "-uid", "-gid", "-nouser", "-nogroup", "-links", "-inum", "-samefile", "-newer",
    "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-daystart", "-maxdepth",
    "-mindepth", "-depth", "-prune", "-quit", "-xdev", "-mount", "-follow", "-readable",
    "-writable", "-executable", "-true", "-false", "-print", "-print0", "-printf", "-ls",
    "-not", "-o", "-or", "-a", "-and", "-H", "-L", "-P", "-regextype",
})

_approved = []  # gated commands the user said yes to, each good for one run


def command_argv(command: str, cwd=None):
    """The exact argv an allow-listed command runs with, or None if it needs the user's OK.

    Allow-listed commands run without a shell, so what was checked is what
    runs: no expansion can turn a safe word into -delete. Only ~ and globs are
    expanded, here; a glob that would expand to an option asks first.
    """
    command = command.strip()
    if not command or any(token in command for token in SHELL_OPERATORS + EXPANSIONS):
        return None
    try:
        words = shlex.split(command)
    except ValueError:  # unbalanced quotes
        return None
    if not words or words[0] not in SAFE_COMMANDS:
        return None
    program, argv = words[0], [words[0]]
    for word in words[1:]:
        if word.startswith("~"):
            word = os.path.expanduser(word)
        if program != "find" and any(c in word for c in GLOB_CHARS):  # find matches patterns itself
            matches = sorted(glob.glob(word, root_dir=None if os.path.isabs(word) else cwd))
            if any(match.startswith("-") for match in matches):
                return None
            argv += matches or [word]  # no match: passed as is, like bash
        else:
            argv.append(word)
    if program == "find" and any(w.startswith("-") and w not in FIND_READ_ONLY for w in argv[1:]):
        return None
    return argv


def needs_confirmation(command: str) -> bool:
    """True unless the command is one allow-listed, read-only command (see command_argv)."""
    return command_argv(command) is None


def approve(command: str) -> None:
    """The user said yes to this gated command: let run_command run it once, in bash."""
    _approved.append(command)


def _run(args, shell: bool):
    process = subprocess.Popen(
        args,
        shell=shell,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        executable="/bin/bash" if shell else None,
        start_new_session=True,  # own process group, so a timeout kills its children too
    )
    try:
        stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return None, None, None
    return process.returncode, stdout, stderr


@tool
def run_command(command: str) -> str:
    """Run a shell command and return the output."""
    argv = command_argv(command)
    if argv is not None:
        returncode, stdout, stderr = _run(argv, shell=False)
    elif command in _approved:  # gated: runs only after the user's yes, once
        _approved.remove(command)
        returncode, stdout, stderr = _run(command, shell=True)
    else:
        return "Error: this command needs the user's confirmation first."

    if returncode is None:
        logger.error(f"Command timed out after {COMMAND_TIMEOUT}s: {command}")
        return f"Error: command timed out after {COMMAND_TIMEOUT}s"
    if returncode != 0:
        logger.error(f"Error executing command: {command}\nError: {stderr}")
        return f"Error: {stderr}"
    logger.info(f"Command executed successfully: {stdout}")
    return stdout
