"""
Interactive CLI Chat (chat_cli)
===============================

A terminal-based chat session for the zkzkAgent project — similar in spirit to
the Claude / Codex CLIs. It binds the conversation to a (dummy) user and
session, streams the assistant's reply live, supports ↑/↓ history recall, and
keeps the noisy internal agent logs out of the way unless you ask for them.

Run it via the launcher:
    ./cli.sh                 # normal
    ./cli.sh --verbose       # show the agent's internal INFO logs
    ./cli.sh --debug         # show everything (DEBUG)
    ./cli.sh --user alice    # override the dummy user id

or directly:
    python -m chat_cli
"""

import argparse
import contextlib
import io
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # Load .env before any module reads os.getenv()

from . import ui
from .commands import handle_command
from .logging_setup import configure_logging, set_level, set_verbose
from .session import ChatSession
from .ui import C, rule, style

log = logging.getLogger("chat")

HISTORY_FILE = os.path.expanduser("~/.zkzkagent_chat_history")


_input_session = None


def setup_input() -> None:
    """Create a prompt_toolkit session when stdin is a TTY; else stay on input()."""
    global _input_session
    if not sys.stdin.isatty():
        return  # piped input — plain input() is correct and avoids ptk on a pipe
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
    except ImportError:
        return  # not installed — input() still works (without the wrap fix)
    _input_session = PromptSession(history=FileHistory(HISTORY_FILE))


def read_user_input(prompt: str) -> str:
    """Read one line. prompt_toolkit when available, else stdlib input().

    `prompt` carries ANSI color codes (empty when not a TTY); prompt_toolkit's
    ANSI() parser measures it correctly, so no readline \\001/\\002 markers are
    needed. Raises EOFError / KeyboardInterrupt like input() does.
    """
    if _input_session is not None:
        from prompt_toolkit.formatted_text import ANSI

        return _input_session.prompt(ANSI(prompt)).strip()
    return input(prompt).strip()


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #
def load_runtime(verbose_default: bool):
    """
    Import the heavy agent graph while showing INFO logs so the ~5s init isn't
    a silent wait. Returns (app, model_name). Logging level is restored to the
    user's chosen verbosity afterwards.
    """
    set_level(logging.INFO)  # show init progress regardless of --verbose
    log.info("loading agent runtime…")
    start = time.time()
    from core.agent import app
    from models.LLM import MODEL_NAME

    log.info("agent graph imported in %.1fs", time.time() - start)
    if not verbose_default:
        set_verbose(False)  # back to quiet for the chat itself
    return app, MODEL_NAME


def warm_up(app, verbose_default: bool) -> None:
    from langchain_core.messages import HumanMessage

    set_level(logging.INFO)  # surface the model warm-up steps
    log.info("warming up model…")
    start = time.time()
    warm_state = ChatSession.fresh_state()
    warm_state["messages"] = [
        HumanMessage(content="this is a warm up message, generate a short response"),
    ]
    try:
        # Swallow the throwaway warm-up reply that the nodes stream to stdout.
        with contextlib.redirect_stdout(io.StringIO()):
            app.invoke(warm_state)
        log.info("model ready in %.1fs", time.time() - start)
    except Exception as exc:  # noqa: BLE001 — surface, don't crash startup
        log.error("warm-up failed: %s", exc)
        print(
            style(
                "  the model could not be reached — is Ollama running? "
                "you can still type, but requests will error.",
                C.YELLOW,
            )
        )
    finally:
        if not verbose_default:
            set_verbose(False)

def run_turn(app, session: ChatSession, user_input: str) -> None:
    from langchain_core.messages import HumanMessage

    session.state["messages"].append(HumanMessage(content=user_input))
    session.state["iteration_count"] = 0  # reset step counter for the new request
    session.turns += 1

    print(style(rule(), C.GREY))
    start = time.time()
    try:
        session.state = app.invoke(session.state)
    except KeyboardInterrupt:
        print(style("\n  ⏹ request interrupted", C.YELLOW))
        return
    except Exception as exc:  # noqa: BLE001 — keep the REPL alive
        log.error("agent error: %s", exc)
        print(style(f"  ✖ the agent raised an error: {exc}", C.RED))
        return

    ui.render_assistant_final(session)
    took = time.time() - start
    print(style(f"  {took:.1f}s · session {session.session_id}", C.GREY, C.DIM))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chat_cli", description="Interactive CLI chat for the zkzkAgent project."
    )
    parser.add_argument(
        "--user", default=os.getenv("CHAT_USER", "local-user"),
        help="dummy user id to bind the session to (default: local-user)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show the agent's internal INFO logs",
    )
    parser.add_argument(
        "--debug", action="store_true", help="show all logs (DEBUG)",
    )
    args = parser.parse_args()

    configure_logging(verbose=args.verbose, debug=args.debug)
    verbose_default = args.verbose or args.debug
    verbose_state = {"on": verbose_default}

    # Draw the logo first thing — instant, before any heavy import.
    ui.draw_logo()
    ui.print_tagline()

    setup_input()
    session = ChatSession(user_id=args.user)

    app, model_name = load_runtime(verbose_default)
    ui.print_meta(session, model_name)
    log.info("starting chat for user=%s session=%s", session.user_id, session.session_id)

    warm_up(app, verbose_default)
    print()

    prompt = style("you ", C.CYAN, C.BOLD) + style("› ", C.CYAN)
    while True:
        try:
            user_input = read_user_input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_command(user_input, session, verbose_state):
                break
            continue

        run_turn(app, session, user_input)

    print(style("  bye", C.MAGENTA))
    log.info("ending session %s after %d turns", session.session_id, session.turns)


if __name__ == "__main__":
    main()
