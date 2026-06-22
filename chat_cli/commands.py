"""In-session slash commands."""

from . import ui
from .logging_setup import set_verbose
from .session import ChatSession
from .ui import C, style


def handle_command(cmd: str, session: ChatSession, verbose_state: dict) -> bool:
    """Return True if the loop should continue, False to exit."""
    name = cmd.lstrip("/").strip().lower()

    if name in ("exit", "quit", "q"):
        return False
    if name in ("help", "h", "?"):
        print(ui.HELP_TEXT)
    elif name == "reset":
        session.reset()
        print(style(f"  ✦ new session {session.session_id}", C.MAGENTA))
    elif name == "history":
        ui.print_history(session)
    elif name == "session":
        ui.print_session_info(session)
    elif name == "verbose":
        verbose_state["on"] = not verbose_state["on"]
        set_verbose(verbose_state["on"])
        state = "ON" if verbose_state["on"] else "OFF"
        print(style(f"  ✦ internal logs {state}", C.MAGENTA))
    else:
        print(style(f"  unknown command: /{name} (try /help)", C.YELLOW))
    return True
