from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from core.state import AgentState
import logging
from core.loadPrompts import LoadPrompts
from agent_nodes._stream import stream_to_stdout
from agent_nodes.handover import PLAN_HINT
from models.selector import AllBackendsFailed, current, run_role


load_prompts = LoadPrompts()
planning_prompt = load_prompts.load_prompt("planner.yaml")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def plan_node(state: AgentState) -> AgentState:
    # Use only the last user message for a focused plan — no history noise
    messages = state.get("messages", [])
    last_user_msg = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
        "",
    )
    rationale = state.get("router_rationale", "")

    # Build a focused planning input: user request + router's reasoning
    planning_input = f"User request: {last_user_msg}"
    if rationale:
        planning_input += f"\nContext (why planning is needed): {rationale}"

    plan_input = [
        SystemMessage(planning_prompt[0].content),
        HumanMessage(content=planning_input),
    ]
    try:
        # Planning sees only the request, so a failed backend can be swapped mid-reply
        response, backend = run_role(
            "plan", lambda chat, backend: (stream_to_stdout(chat.stream(plan_input)), backend)
        )
    except AllBackendsFailed as e:
        text = e.user_message()
        logger.error(f"[PLANNING] {text}")
        print(f"\n[AI]: {text}\n")
        return {"messages": [AIMessage(content=text)], "pending_plan": None}
    content = (response.content if response is not None else "").strip()

    if not content:
        # Never end a planning turn silently — the stream produced nothing.
        content = "I couldn't draft a plan for that. Could you rephrase the request?"
        print(f"\n[AI]: {content}\n")
        logger.warning("[PLANNING] Empty plan — emitted fallback message")
        return {"messages": [AIMessage(content=content)], "pending_plan": None}

    sel = current()
    primary = sel.primary("plan")
    if backend != primary:
        note = (
            f"\n\n(Planned by {sel.label(backend)} because {sel.label(primary)} failed: "
            f"{sel.why('plan', primary)})"
        )
        print(note.strip())
        content += note

    print(PLAN_HINT + "\n")
    logger.info("[PLANNING] Plan generated — awaiting approval")
    return {
        "messages": [AIMessage(content=content + PLAN_HINT)],
        "pending_plan": content,
    }
