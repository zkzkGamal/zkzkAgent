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

def safe_json_parse(raw: str) -> Dict[str, Any]:
    """More forgiving JSON extraction"""
    # Remove code fences, thinking traces, etc.
    cleaned = re.sub(r'^.*?(?=\{)', '', raw, flags=re.DOTALL)   # strip before first {
    cleaned = re.sub(r"```json|```", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except JSONDecodeError:
        # Last-ditch: try to find the outermost {…}
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except JSONDecodeError:
                pass
        return {}

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

    if len(query) > 4000:
        query = query[:3800] + "\n… [truncated]"

    try:
        response = get_router_chain().invoke([
            SystemMessage(content=system_content),
            HumanMessage(content=query),
        ]).content
    except Exception as e:
        logger.exception("[ROUTER] LLM call failed")
        return {"category": "CONVERSATIONAL", "router_rationale": f"LLM error: {str(e)}"}

    logger.debug(f"[ROUTER] Raw:\n{response}")

    parsed = safe_json_parse(response)
    category = parsed.get("route", "CONVERSATIONAL")

    # Optional: normalize categories (prevents downstream breakage)
    valid_categories = {"CONVERSATIONAL", "NEEDS_PLANNING", "DIRECT_EXECUTION"}
    if category not in valid_categories:
        logger.warning(f"[ROUTER] Invalid category '{category}' → fallback")
        category = "CONVERSATIONAL"

    rationale = parsed.get("rationale", "").strip()[:300]  # prevent state bloat

    logger.info(f"[ROUTER] → {category} | {rationale[:80]}{'…' if len(rationale) > 80 else ''}")
    return {"category": category, "router_rationale": rationale}