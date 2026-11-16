import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from preprocessing.get_clean_history import CONFIRM_TAG, get_clean_history
from core.state import AgentState
from core.loadPrompts import LoadPrompts
from core.tools import __all__ as tool_functions
from models.selector import AUTH_HINT, classify_error, current, error_text
from agent_nodes._stream import stream_to_stdout
from agent_nodes.handover import (
    CANCELED_RESULT, SKIPPED_RESULT, build_handover, done_steps, is_continue, is_retry, plan_text,
    task_start,
)
from tools_module.runCommand import approve, needs_confirmation


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_prompts = LoadPrompts()
execution_prompt = load_prompts.load_prompt("executor.yaml")

DANGEROUS_TOOLS = [
    "empty_trash",
    "clear_tmp",
    "remove_file",
    "install_package",
    "remove_package",
    "run_deploy_script",
]
CONFIRM_WORDS = ("yes", "y")
NO_CONFIRMATION = {"tool_name": None, "tool_args": None, "tool_call_id": None}


def needs_confirmation_call(call: dict) -> bool:
    """Dangerous tools always ask; run_command asks unless the command is allow-listed."""
    if call["name"] in DANGEROUS_TOOLS:
        return True
    command = str((call.get("args") or {}).get("command", ""))
    return call["name"] == "run_command" and needs_confirmation(command)


def _command_of(call: dict):
    args = call.get("args") or {}
    for key in ("command", "installation_command", "remove_command"):
        if args.get(key):
            return str(args[key])
    return None


def confirmation_text(call: dict) -> str:
    """What the user is asked, naming the real action."""
    name, args = call["name"], call.get("args") or {}
    command = _command_of(call)
    actions = {
        "run_command": f"run this command:\n  {command}",
        "install_package": f"install software with this command:\n  {command}",
        "remove_package": f"uninstall software with this command:\n  {command}",
        "remove_file": f"permanently delete {args.get('path', 'a file')}",
        "empty_trash": "permanently delete everything in your trash",
        "clear_tmp": "permanently delete everything in /tmp",
        "run_deploy_script": "run your deploy script, using your GPG password",
    }
    action = actions.get(name) or f"call {name} with {json.dumps(args, default=str)}"
    return f"I'm about to {action}\nReply 'yes' to go ahead or 'no' to cancel."


def cancel_text(call: dict) -> str:
    command = _command_of(call)
    return f"Canceled: I did not run `{command}`." if command else f"Canceled: I did not run {call['name']}."


def _answer_confirmation(state: AgentState, pending: dict):
    """Run (or cancel) the call the user was asked about.

    Returns the ToolMessages that answer every call in the paused AI message,
    whether the user said yes, and the call itself.
    """
    messages = state.get("messages", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    answer = (last_human.content if last_human else "").strip().lower().rstrip("!.")
    call_id = pending.get("tool_call_id")
    paused = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage) and m.tool_calls
         and any(c["id"] == call_id or (call_id is None and c["name"] == pending["tool_name"])
                 for c in m.tool_calls)),
        None,
    )
    calls = paused.tool_calls if paused else []
    call = next(
        (c for c in calls if c["id"] == call_id or (call_id is None and c["name"] == pending["tool_name"])),
        {"name": pending["tool_name"], "args": pending.get("tool_args") or {}, "id": call_id},
    )
    approved = answer in CONFIRM_WORDS
    logger.info(f"[AGENT] Confirmation for {call['name']}: user said {answer!r}")

    if approved:
        if call["name"] == "run_command":
            approve(str((call.get("args") or {}).get("command", "")))
        tool = next((t for t in tool_functions if t.name == call["name"]), None)
        try:
            output = tool.invoke(call["args"]) if tool else f"Error: unknown tool {call['name']}"
        except Exception as e:  # noqa: BLE001 — the model sees the error, like ToolNode
            output = f"Error: {e}"
        result = str(output)
    else:
        result = CANCELED_RESULT

    answers = []
    if call.get("id"):
        answers.append(ToolMessage(content=result, tool_call_id=call["id"], name=call["name"]))
    elif approved:  # no id to pair with: keep the output visible the old way
        answers.append(HumanMessage(content=f"[TOOL OUTPUT] {result}"))
    answers += [
        ToolMessage(content=SKIPPED_RESULT, tool_call_id=c["id"], name=c["name"])
        for c in calls if c["id"] != call.get("id")
    ]
    return answers, approved, call


def _last_human_text(messages: list) -> str:
    last = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    return str(last.content) if last else ""


def retry_note(messages: list) -> str:
    """What the model is told when the user retries a stopped task: the truth about what ran."""
    start = task_start(messages)
    steps = done_steps(messages, start)
    if steps:
        names = ", ".join(step.split("(", 1)[0] for step in steps)
        return (
            "Continue the task from where it stopped. These steps already ran; "
            f"do not redo them: {names}."
        )
    what = "carry out the approved plan above from step 1" if plan_text(messages, start) else "do the task"
    return f"Nothing has run yet. Start again: {what}."


def _choose_backend(state: AgentState, sel, messages: list):
    """Pick the executor's model for this call. Never switches inside a task.

    Returns (backend, takeover, updates, note): `takeover` is the handover in
    force, if any, and `note` is the unsaved instruction for a retry.
    """
    interrupted = state.get("interrupted")
    takeover = state.get("takeover")
    text = _last_human_text(messages)
    if interrupted and is_continue(text) and interrupted.get("can_continue"):
        backend = sel.other(interrupted["backend"])
        start = next(i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage))
        takeover = {"text": interrupted["handover"], "start": start}
        logger.info(f"[AGENT] Continuing the stopped task on {sel.label(backend)} from a handover")
        return backend, takeover, {"interrupted": None, "takeover": takeover}, None
    if interrupted and (is_retry(text) or is_continue(text)):
        backend = interrupted["backend"]
        sel.reset(backend)  # the user asked for it: try even inside the cooldown
        logger.info(f"[AGENT] Retrying the stopped task on {sel.label(backend)}")
        return backend, takeover, {"interrupted": None}, retry_note(messages)
    if takeover:
        return state.get("exec_backend") or sel.other(sel.primary("execute")), takeover, {}, None
    if not state.get("iteration_count"):  # a new turn: the only point where the model may change
        return sel.order("execute")[0], None, {}, None
    return state.get("exec_backend") or sel.order("execute")[0], None, {}, None


def _model_input(sel, backend: str, takeover, messages: list) -> list:
    """What the executor's model sees. A model that is not the primary never gets
    another model's long history: a handover summary, or only this task."""
    if takeover:
        tail = messages[takeover["start"]:]
        return [HumanMessage(content=takeover["text"]), *get_clean_history({"messages": tail})]
    if backend != sel.primary("execute"):
        return get_clean_history({"messages": messages[task_start(messages):]})
    return get_clean_history({"messages": messages})


def _stop_task(sel, backend: str, exc: Exception, messages: list, new_messages: list, updates: dict):
    """The model failed mid-task: keep everything done so far and ask what to do."""
    label = sel.label(backend)
    start = task_start(messages)
    steps = done_steps(messages, start)
    reason = f"{label} stopped: {error_text(exc)}"
    other = sel.other(backend)
    can_continue = bool(other and sel.fallback and sel.breakers[other].available())

    if steps:
        names = [step.split("(", 1)[0] for step in steps]
        shown = ", ".join(names[:6]) + (", …" if len(names) > 6 else "")
        progress = f"Nothing is lost: {len(steps)} step{'s' if len(steps) > 1 else ''} of this task {'are' if len(steps) > 1 else 'is'} done ({shown})."
    else:
        progress = "No steps of this task had run yet."
    auth = classify_error(exc) == "auth"
    retry = f"'retry' to try {label} again" + (" once your credits are topped up" if auth else "")
    if can_continue:
        ask = f"Reply 'continue' to finish with {sel.label(other)}, or {retry}. "
        ask += (
            "The local model is smaller, so it gets a short summary of what is done instead of the full history."
            if other == "local" else f"{sel.label(other)} gets a short summary of what is done."
        )
    else:
        ask = f"Reply {retry}."
    hint = f"\n{AUTH_HINT}" if auth else ""
    text = f"{reason.rstrip('.')}.{hint}\n{progress}\n{ask}"
    print(f"\n[AI]: {text}\n")
    logger.warning(f"[AGENT] Task stopped: {reason}")
    return {
        **updates,
        "messages": [*new_messages, AIMessage(content=text)],
        "interrupted": {
            "backend": backend,
            "error": error_text(exc),
            "handover": build_handover(messages, start, reason),
            "can_continue": can_continue,
        },
        "exec_backend": backend,
        "pending_plan": None,
    }


def execute_node(state: AgentState):
    """
    The main agent node.
    It handles:
    1. Checking for pending confirmations.
    2. Invoking the LLM.
    """
    pending = state.get("pending_confirmation") or {}
    new_messages = []  # added by this node before the model call
    updates = {}

    # 1. Handle Pending Confirmation: "yes" runs the tool and the task carries on
    if pending.get("tool_name"):
        new_messages, approved, call = _answer_confirmation(state, pending)
        if not approved:
            text = cancel_text(call)
            print(f"\n[AI]: {text}\n")
            return {
                "messages": [*new_messages, AIMessage(content=text)],
                "pending_confirmation": dict(NO_CONFIRMATION),
            }
        updates["pending_confirmation"] = dict(NO_CONFIRMATION)

    sel = current()
    all_messages = [*state.get("messages", []), *new_messages]
    backend, takeover, choice, note = _choose_backend(state, sel, all_messages)
    updates.update(choice, exec_backend=backend)
    messages = [SystemMessage(execution_prompt[0].content), *_model_input(sel, backend, takeover, all_messages)]
    if note:
        messages.append(HumanMessage(content=note))

    logger.info(f"[AGENT] Processing with {len(messages)} messages in context")
    if len(messages) > 1:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            logger.info(
                f"[AGENT] Last message: {str(last_msg.content)[:100]}..."
            )  # First 100 chars

    # If the user just approved a pending plan, inject it as an explicit
    # instruction so the executor carries it out instead of replanning.
    pending_plan = state.get("pending_plan")
    if pending_plan:
        logger.info("[AGENT] Executing approved plan")
        messages.append(
            HumanMessage(
                content=(
                    "I approve the plan below. Execute it now: call the necessary "
                    "tools, then give me the final answer.\n\n" + pending_plan
                )
            )
        )

    try:
        response = stream_to_stdout(sel.chat(backend, tool_functions).stream(messages))
    except Exception as exc:  # noqa: BLE001 — any model failure stops the task cleanly
        sel.record("execute", backend, exc)
        return _stop_task(sel, backend, exc, all_messages, new_messages, updates)
    sel.record("execute", backend, None)
    logger.info(f"[AGENT] Response finished")
    if response is None or not response.tool_calls:
        updates["takeover"] = None  # the task is finished (or gave up): back to normal

    # Anything that needs the user's OK pauses the task here
    if response is not None and response.tool_calls:
        for tc in response.tool_calls:
            if needs_confirmation_call(tc):
                logger.info(f"[AGENT] Confirmation needed for: {tc['name']}")
                return {
                    "messages": [
                        *new_messages,
                        response,
                        HumanMessage(
                            content=confirmation_text(tc),
                            additional_kwargs={"zkzk": CONFIRM_TAG},
                        ),
                    ],
                    "pending_confirmation": {
                        "tool_name": tc["name"],
                        "tool_args": tc["args"],
                        "tool_call_id": tc["id"],
                    },  # one confirmation at a time; the other calls get "Not run"
                    "pending_plan": None,  # plan (if any) is now being executed
                    **{k: v for k, v in updates.items() if k != "pending_confirmation"},
                }

    # The stream produced nothing usable (no text, no tool calls) — emit a
    # visible fallback so the turn is never silent.
    if response is None or (
        not (response.content or "").strip() and not response.tool_calls
    ):
        fallback = "I wasn't able to produce a response for that. Could you rephrase?"
        print(f"\n[AI]: {fallback}\n")
        logger.warning("[AGENT] Empty response — emitted fallback message")
        return {"messages": [*new_messages, AIMessage(content=fallback)], "pending_plan": None, **updates}

    return {"messages": [*new_messages, response], "pending_plan": None, **updates}
