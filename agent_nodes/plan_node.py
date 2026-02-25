from preprocessing.get_clean_history import get_clean_history
from langchain_core.messages import SystemMessage
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


DANGEROUS_TOOLS = ["empty_trash", "clear_tmp", "remove_file" , "install_package", "remove_package"]


def plan_node(state: AgentState) -> AgentState:
    user_messages = get_clean_history(state)
    planning_chain = get_model_chain()
    response = planning_chain.invoke(
        [SystemMessage(planning_prompt[0].content), *user_messages]
    ).content
    logger.info(f"[PLANNING] Cleaned text: {response}")
    return {"messages": [response]}
