from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from core.state import AgentState
import logging
from models.LLM import llm
from core.loadPrompts import LoadPrompts
from agent_nodes._stream import stream_to_stdout


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

    response = stream_to_stdout(
        llm.stream(
            [
                SystemMessage(planning_prompt[0].content),
                HumanMessage(content=planning_input),
            ]
        )
    )
    content = (response.content if response is not None else "").strip()

    if not content:
        # Never end a planning turn silently — the stream produced nothing.
        content = "I couldn't draft a plan for that. Could you rephrase the request?"
        print(f"\n[AI]: {content}\n")
        logger.warning("[PLANNING] Empty plan — emitted fallback message")
        return {"messages": [AIMessage(content=content)], "pending_plan": None}


    hint = "\nReply 'ok' (or 'yes') to run this plan, or tell me what to change."
    print(hint + "\n")
    logger.info("[PLANNING] Plan generated — awaiting approval")
    return {
        "messages": [AIMessage(content=content + hint)],
        "pending_plan": content,
    }
