from core.state import AgentState
import re
import json, logging
from core.loadPrompts import LoadPrompts
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from models.selector import AllBackendsFailed, run_role
from typing import Dict, Any
from json import JSONDecodeError


load_prompts = LoadPrompts()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_json_parse(raw: str) -> Dict[str, Any]:
    cleaned = re.sub(r'^.*?(?=\{)', '', raw, flags=re.DOTALL)
    cleaned = re.sub(r"```json|```", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except JSONDecodeError:
        start = cleaned.find('{')
        end = cleaned.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except JSONDecodeError:
                pass
        return {}

def classify_node(state: AgentState) -> AgentState:
    query = state["messages"][-1].content
    logger.info(f"[ROUTER] Query: {query}")

    router_prompt_messages = load_prompts.load_prompt("router.yaml")
    system_content = router_prompt_messages[0].content

    if len(query) > 4000:
        query = query[:3800] + "\n… [truncated]"

    router_input = [SystemMessage(content=system_content), HumanMessage(content=query)]
    try:
        # The router only classifies: no tools, and no history, so any backend can do it
        response = run_role("classify", lambda chat, backend: chat.invoke(router_input).content)
    except AllBackendsFailed as e:
        text = e.user_message()
        logger.error(f"[ROUTER] {text}")
        print(f"\n[AI]: {text}\n")
        # category None ends the turn (see route_after_classify)
        return {
            "messages": [AIMessage(content=text)],
            "category": None,
            "router_rationale": "",
            "pending_plan": None,
            "interrupted": None,
            "takeover": None,
        }

    logger.debug(f"[ROUTER] Raw:\n{response}")

    parsed = safe_json_parse(response)
    category = parsed.get("route", "CONVERSATIONAL")

    valid_categories = {"CONVERSATIONAL", "NEEDS_PLANNING", "DIRECT_EXECUTION"}
    if category not in valid_categories:
        logger.warning(f"[ROUTER] Invalid category '{category}' → fallback")
        category = "CONVERSATIONAL"

    rationale = parsed.get("rationale", "").strip()[:300]

    logger.info(f"[ROUTER] → {category} | {rationale[:80]}{'…' if len(rationale) > 80 else ''}")
    # Reaching the classifier means this message wasn't a plan approval or a
    # retry/continue (those bypass classify via route_entry), so it starts a
    # new task: drop any stale plan and any stopped task.
    return {
        "category": category,
        "router_rationale": rationale,
        "pending_plan": None,
        "interrupted": None,
        "takeover": None,
    }