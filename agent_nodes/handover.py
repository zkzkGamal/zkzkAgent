"""Words, texts and the handover summary shared by the nodes and the router.

When the executor's model fails mid-task, the next model must not inherit the
whole history: on 15 Nov a 2B finishing a 27B task with its ~5,000-token
history passed 0 of 7. It gets build_handover() instead: the request, the plan
and the steps already done, in a few hundred tokens.
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Appended to every plan the planner shows; the user replies "ok" to run it.
PLAN_HINT = "\nReply 'ok' (or 'yes') to run this plan, or tell me what to change."

# Short approvals that mean "yes, run the plan you just showed me".
PLAN_APPROVALS = {
    "ok", "okay", "k", "kk", "yes", "y", "yeah", "yep", "yup", "sure",
    "go", "go ahead", "do it", "proceed", "continue", "execute", "run it",
    "run", "sounds good", "approved", "approve", "lets go", "let's go",
}
CONFIRM_ANSWERS = {"yes", "y", "no", "n"}
# After a model failure: finish on the other model, or try the same one again
CONTINUE_WORDS = {"continue", "c", "resume", "go on", "finish it"}
RETRY_WORDS = {"retry", "r", "try again"}

# Tool results the executor writes for calls that did not really run
CANCELED_RESULT = "Canceled by the user. Do not try to do this another way."
SKIPPED_RESULT = (
    "Not run: it was waiting on the user's confirmation. Call it again if it is still needed."
)
_NOT_RUN = (CANCELED_RESULT, SKIPPED_RESULT, "Not run.")
_SYNTHETIC_PREFIXES = ("[TOOL OUTPUT]", "[TOOL ERROR]", "[SAFEGUARD]")

MAX_REQUEST = 1000
MAX_PLAN = 2500
MAX_STEPS = 1800  # with the other caps, keeps the whole brief under MAX_HANDOVER
MAX_HANDOVER = 6000
STEP_PART = 120  # characters kept of each step's arguments and of its result


def normalize(text) -> str:
    return str(text).strip().lower().rstrip("!.")


def is_plan_approval(text) -> bool:
    return normalize(text) in PLAN_APPROVALS


def is_continue(text) -> bool:
    return normalize(text) in CONTINUE_WORDS


def is_retry(text) -> bool:
    return normalize(text) in RETRY_WORDS


def _cut(text, limit: int, flat: bool = False) -> str:
    text = " ".join(str(text).split()) if flat else str(text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_control(message: HumanMessage) -> bool:
    """A reply that steers the task ("ok", "yes", "continue"…) rather than starting one."""
    if (message.additional_kwargs or {}).get("zkzk"):
        return True
    text = message.content if isinstance(message.content, str) else str(message.content)
    if text.strip().startswith(_SYNTHETIC_PREFIXES):
        return True
    return normalize(text) in PLAN_APPROVALS | CONFIRM_ANSWERS | CONTINUE_WORDS | RETRY_WORDS


def task_start(messages: list) -> int:
    """Index of the user message that started the current task (0 if none)."""
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        if isinstance(message, HumanMessage) and not _is_control(message):
            return i
    return 0


def done_steps(messages: list, start: int) -> list:
    """Tool calls since `start` that really ran, one line each."""
    results = {m.tool_call_id: m for m in messages[start:] if isinstance(m, ToolMessage)}
    steps = []
    for message in messages[start:]:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls or []:
            result = results.get(call["id"])
            if result is None or str(result.content).startswith(_NOT_RUN):
                continue
            args = ", ".join(f"{k}={v}" for k, v in (call.get("args") or {}).items())
            output = _cut(result.content, STEP_PART, flat=True) or "(no output)"
            steps.append(f"{call['name']}({_cut(args, STEP_PART, flat=True)}) → {output}")
    return steps


def plan_text(messages: list, start: int):
    """The plan the user approved for this task, without the approval hint."""
    for message in messages[start:]:
        content = message.content if isinstance(message, AIMessage) else None
        if isinstance(content, str) and not message.tool_calls and content.endswith(PLAN_HINT):
            return content[: -len(PLAN_HINT)].strip()
    return None


def build_handover(messages: list, start: int, reason: str) -> str:
    """A short brief for the model taking over: request, plan, steps done."""
    request = messages[start].content if start < len(messages) else ""
    plan = plan_text(messages, start)
    steps = done_steps(messages, start)

    shown, size = [], 0
    for step in reversed(steps):  # keep the latest steps if there are many
        if size + len(step) > MAX_STEPS:
            break
        shown.insert(0, step)
        size += len(step) + 3
    if len(shown) < len(steps):
        shown.insert(0, f"…and {len(steps) - len(shown)} earlier steps")

    parts = [
        f"You are taking over a task that another model started. It stopped because: {_cut(reason, 300, flat=True)}",
        f"The user's request:\n{_cut(request, MAX_REQUEST)}",
    ]
    if plan:
        parts.append(f"The plan the user approved (shortened):\n{_cut(plan, MAX_PLAN)}")
    parts.append(
        "Already done, do not redo these:\n" + "\n".join(f"- {s}" for s in shown)
        if shown else "Nothing has been done yet."
    )
    parts.append("Do the remaining steps with your tools, then reply with a short summary.")
    return "\n\n".join(parts)[:MAX_HANDOVER]
