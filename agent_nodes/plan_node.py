from langchain_core.messages import SystemMessage, HumanMessage
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

    # Planning ONLY writes the plan — bind no tools so the model can't start
    # executing here. The graph stops after this node (plan → END) so the user
    # can review the plan and then approve it. Stream it live so the CLI shows
    # the plan as it is written instead of silently generating it.
    response = stream_to_stdout(
        llm.stream(
            [
                SystemMessage(planning_prompt[0].content),
                HumanMessage(content=planning_input),
            ]
        )
    )
    content = response.content if response is not None else ""
    logger.info("[PLANNING] Plan generated")
    return {"messages": [content]}
