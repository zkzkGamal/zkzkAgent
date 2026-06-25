"""Terminal styling, the zkzkAgent logo, and rendering helpers."""

import os
import sys
import time
from datetime import datetime


# --------------------------------------------------------------------------- #
# Minimal ANSI styling (no extra dependency; auto-disables when not a TTY)
# --------------------------------------------------------------------------- #
class C:
    _on = sys.stdout.isatty() and os.getenv("NO_COLOR") is None

    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""
    ITALIC = "\033[3m" if _on else ""

    RED = "\033[31m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    BLUE = "\033[34m" if _on else ""
    MAGENTA = "\033[35m" if _on else ""
    CYAN = "\033[36m" if _on else ""
    GREY = "\033[90m" if _on else ""


def style(text: str, *codes: str) -> str:
    return f"{''.join(codes)}{text}{C.RESET}"


# Readline's "non-printing" markers. Wrapping ANSI codes in these tells readline
# they take up zero columns, so it measures the prompt width correctly. Without
# them, a wrapped input line corrupts the redraw (eats the first line and the
# "you ›" prompt, then shows your text starting on line 2).
RL_START = "\001"  # \x01 — start of ignored (zero-width) sequence
RL_END = "\002"  # \x02 — end of ignored sequence


def prompt_style(text: str, *codes: str) -> str:
    """Like style(), but readline-safe — for strings passed to input()."""
    if not codes or not C._on:
        return text
    open_codes = RL_START + "".join(codes) + RL_END
    close = RL_START + C.RESET + RL_END
    return f"{open_codes}{text}{close}"


def term_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def rule(label: str = "", color: str = C.GREY) -> str:
    width = min(term_width(), 80)
    if not label:
        return style("─" * width, color)
    label = f" {label} "
    side = (width - len(label)) // 2
    return style("─" * side + label + "─" * (width - side - len(label)), color)


# --------------------------------------------------------------------------- #
# Logo — ANSI Shadow wordmark, reads "zkzkAgent" stacked as ZKZK / AGENT.
# Revealed one line at a time, like the bash draw_logo().
# --------------------------------------------------------------------------- #
_LOGO_ZKZK = [
    "  ███████╗██╗  ██╗███████╗██╗  ██╗",
    "  ╚══███╔╝██║ ██╔╝╚══███╔╝██║ ██╔╝",
    "    ███╔╝ █████╔╝   ███╔╝ █████╔╝ ",
    "   ███╔╝  ██╔═██╗  ███╔╝  ██╔═██╗ ",
    "  ███████╗██║  ██╗███████╗██║  ██╗",
    "  ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
]

_LOGO_AGENT = [
    "   █████╗   ██████╗  ███████╗ ███╗   ██╗ ████████╗",
    "  ██╔══██╗ ██╔════╝  ██╔════╝ ████╗  ██║ ╚══██╔══╝",
    "  ███████║ ██║  ███╗ █████╗   ██╔██╗ ██║    ██║   ",
    "  ██╔══██║ ██║   ██║ ██╔══╝   ██║╚██╗██║    ██║   ",
    "  ██║  ██║ ╚██████╔╝ ███████╗ ██║ ╚████║    ██║   ",
    "  ╚═╝  ╚═╝  ╚═════╝  ╚══════╝ ╚═╝  ╚═══╝    ╚═╝   ",
]

# Top band (ZKZK) magenta→cyan, bottom band (AGENT) cyan→blue.
_LOGO = [(line, C.BOLD + C.MAGENTA) for line in _LOGO_ZKZK[:2]]
_LOGO += [(line, C.BOLD + C.CYAN) for line in _LOGO_ZKZK[2:]]
_LOGO += [(line, C.BOLD + C.CYAN) for line in _LOGO_AGENT[:3]]
_LOGO += [(line, C.BOLD + C.BLUE) for line in _LOGO_AGENT[3:]]


def draw_logo(delay: float = 0.02) -> None:
    """Reveal the logo line by line (skip the animation when not a TTY)."""
    animate = delay > 0 and sys.stdout.isatty()
    print()
    for line, color in _LOGO:
        print(style(line, color))
        if animate:
            time.sleep(delay)
    sys.stdout.flush()  # ensure the logo lands before the heavy import logs


def print_tagline() -> None:
    print()
    print(style("  zkzkAgent · interactive chat", C.CYAN, C.BOLD))
    print(style("  type /help for commands, /exit to quit", C.GREY))
    print()


def print_meta(session, model_name: str) -> None:
    meta = [
        ("user", session.user_id),
        ("session", session.session_id),
        ("model", model_name),
    ]
    line = style("  ", C.GREY) + style(" · ", C.GREY).join(
        f"{style(k, C.GREY)} {style(v, C.BOLD)}" for k, v in meta
    )
    print(line)
    print()


def print_banner(session, model_name: str) -> None:
    draw_logo()
    print_tagline()
    print_meta(session, model_name)


# --------------------------------------------------------------------------- #
# Response / history rendering
# --------------------------------------------------------------------------- #
def render_assistant_final(session) -> None:
    """
    Surface anything the live stream did NOT already show.

    Both the execute/plan path and the conversational path stream their reply
    to stdout live, so the assistant's text is already on screen — we do not
    re-print it. What still needs surfacing is the dangerous-tool confirmation
    prompt (appended *after* streaming) and the case where the model only ran
    tools and produced no text.
    """
    from langchain_core.messages import AIMessage
    from preprocessing.strip_think_tags import strip_think_tags

    messages = session.state.get("messages", [])
    if not messages:
        print(style("  (no response)", C.YELLOW))
        return

    last = messages[-1]
    content = getattr(last, "content", last)
    clean = strip_think_tags(content if isinstance(content, str) else str(content))

    if session.awaiting_confirmation:
        print(style("  ⚠ confirmation required", C.YELLOW, C.BOLD))
        print(style(f"  {clean}", C.YELLOW))
        print(style("  reply with 'yes' to proceed or 'no' to cancel", C.GREY))
        return

    if isinstance(last, AIMessage) and not clean.strip():
        print(style("  (the assistant ran tools without a text reply)", C.GREY))


def print_history(session) -> None:
    from langchain_core.messages import AIMessage, HumanMessage
    from preprocessing.strip_think_tags import strip_think_tags

    messages = session.state.get("messages", [])
    if not messages:
        print(style("  history is empty", C.GREY))
        return

    print(rule("history"))
    for msg in messages:
        content = getattr(msg, "content", str(msg))
        if not isinstance(content, str):
            content = str(content)
        content = strip_think_tags(content).strip()
        if not content:
            continue
        if isinstance(msg, HumanMessage):
            who, color = "you", C.CYAN
        elif isinstance(msg, AIMessage):
            who, color = "assistant", C.GREEN
        else:
            who, color = "system", C.GREY
        print(f"{style(who + ':', color, C.BOLD)} {content[:500]}")
    print(rule())


def print_session_info(session) -> None:
    elapsed = datetime.now() - session.started_at
    print(rule("session"))
    print(f"  {style('user', C.GREY)}     {session.user_id}")
    print(f"  {style('session', C.GREY)}  {session.session_id}")
    print(f"  {style('started', C.GREY)}  {session.started_at:%Y-%m-%d %H:%M:%S}")
    print(f"  {style('uptime', C.GREY)}   {int(elapsed.total_seconds())}s")
    print(f"  {style('turns', C.GREY)}    {session.turns}")
    print(rule())


HELP_TEXT = f"""
{style('commands', C.BOLD)}
  {style('/help', C.CYAN)}      show this help
  {style('/reset', C.CYAN)}     start a fresh conversation (new session id)
  {style('/history', C.CYAN)}   print the conversation history
  {style('/verbose', C.CYAN)}   toggle internal agent logs
  {style('/session', C.CYAN)}   show user / session info
  {style('/exit', C.CYAN)}      quit (also: /quit, Ctrl-D, Ctrl-C)

{style('tip', C.GREY)} use ↑ / ↓ to recall previous messages
"""
