from core.state import AgentState
import re
import json, logging
from models.LLM import llm
from core.loadPrompts import LoadPrompts
from core.tools import __all__ as tool_functions
from langchain_core.messages import SystemMessage, HumanMessage


load_prompts = LoadPrompts()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_router_chain = None


def get_router_chain():
    global _router_chain
    if _router_chain is None:
        logger.info("[ROUTER INIT] Lazily initializing router LLM (no tools needed)")
        _router_chain = llm  # router only classifies — no tools needed
        logger.info("[ROUTER INIT] Router initialized")
    else:
        logger.info("[ROUTER INIT] Router already initialized")
    return _router_chain


def classify_node(state: AgentState) -> AgentState:
    # Use the last user message as query
    query = state["messages"][-1].content
    logger.info(f"[ROUTER] Query: {query}")

    # Load prompt fresh (it formats home/name variables internally)
    router_prompt_messages = load_prompts.load_prompt("router.yaml")
    system_content = router_prompt_messages[0].content

    model = get_router_chain()
    response = model.invoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=query),
        ]
    ).content

    logger.info(f"[ROUTER] Raw response: {response}")
    try:
        cleaned_text = re.sub(r"```json|```", "", response).strip()
        parsed = json.loads(cleaned_text)
        category = parsed["route"]
    except (json.JSONDecodeError, KeyError):
        logger.warning(
            "[ROUTER] Failed to parse response, defaulting to CONVERSATIONAL"
        )
        category = "CONVERSATIONAL"

    logger.info(f"[ROUTER] Classified as: {category}")
    return {"category": category}
