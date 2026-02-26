from langchain_core.messages import SystemMessage, HumanMessage
from core.state import AgentState
import logging
from models.LLM import llm
from core.loadPrompts import LoadPrompts
from core.tools import __all__ as tool_functions


load_prompts = LoadPrompts()
planning_prompt = load_prompts.load_prompt("planner.yaml")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_model_chain = None


def get_model_chain():
    global _model_chain
    if _model_chain is None:
        logger.info("[MODEL INIT] Lazily binding tools to ChatOllama")
        _model_chain = llm.bind_tools(tool_functions)
        logger.info("[MODEL INIT] Model initialized and tools bound")
    logger.info("[MODEL INIT] Model already initialized")
    return _model_chain


DANGEROUS_TOOLS = [
    "empty_trash",
    "clear_tmp",
    "remove_file",
    "install_package",
    "remove_package",
]


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

    planning_chain = get_model_chain()
    response = planning_chain.invoke(
        [
            SystemMessage(planning_prompt[0].content),
            HumanMessage(content=planning_input),
        ]
    ).content
    logger.info(f"[PLANNING] Plan generated: {response}")
    return {"messages": [response]}
