from preprocessing.get_clean_history import get_clean_history
from langchain_core.messages import SystemMessage, AIMessage
from core.state import AgentState
import logging
from core.loadPrompts import LoadPrompts
from agent_nodes._stream import stream_to_stdout
from models.selector import AllBackendsFailed, current, run_role


load_prompts = LoadPrompts()
conversational_prompt = load_prompts.load_prompt("conversational.yaml")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# A fallback model only gets the end of the chat: it may have a much smaller window
FALLBACK_HISTORY = 6


def conversation_node(state: AgentState) -> AgentState:
    history = get_clean_history(state, include_tool_messages=False)
    primary = current().primary("conversational")

    def reply(chat, backend):
        messages = history if backend == primary else history[-FALLBACK_HISTORY:]
        # No tools here: the prompt says so, and tool calls from this node were never run.
        # Streams to stdout live so the CLI shows the reply as it is generated.
        return stream_to_stdout(
            chat.stream([SystemMessage(conversational_prompt[0].content), *messages])
        )

    try:
        response = run_role("conversational", reply)
    except AllBackendsFailed as e:
        content = e.user_message()
        logger.error(f"[CONVERSATIONAL] {content}")
        print(f"\n[AI]: {content}\n")
        return {"messages": [AIMessage(content=content)], "pending_plan": None}

    content = (response.content if response is not None else "").strip()
    if not content:
        content = "Got it — what would you like to do next?"
        print(f"\n[AI]: {content}\n")
        logger.warning("[CONVERSATIONAL] Empty reply — emitted fallback message")
    else:
        logger.info(f"[CONVERSATIONAL] Cleaned text: {content}")

    return {"messages": [AIMessage(content=content)], "pending_plan": None}
