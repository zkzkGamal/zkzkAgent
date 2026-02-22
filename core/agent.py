import logging
from typing import Literal
from models.LLM import llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from core.state import AgentState
from core.tools import __all__ as tool_functions

logger = logging.getLogger(__name__)

# -------------------------
# Initialize Model and Tools
# -------------------------
# We lazy-load the chain to avoid import-time side effects
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

# -------------------------
# Node Definitions
# -------------------------


def call_model(state: AgentState):
    """
    The main agent node.
    It handles:
    1. Checking for pending confirmations.
    2. Invoking the LLM.
    """
    messages = state["messages"]
    pending_confirmation = state.get(
        "pending_confirmation", {"tool_name": None, "user_message": None}
    )

    # Debug logging for context tracking
    logger.info(f"[AGENT] Processing with {len(messages)} messages in context")
    if len(messages) > 1:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            logger.info(
                f"[AGENT] Last message: {last_msg.content[:100]}..."
            )  # First 100 chars

    # 1. Handle Pending Confirmation
    if pending_confirmation and pending_confirmation.get("tool_name"):
        tool_name = pending_confirmation["tool_name"]
        last_msg = messages[-1]

        if isinstance(last_msg, HumanMessage):
            confirm = last_msg.content.strip().lower()
            logger.info(
                f"[AGENT] Handling pending confirmation for tool: {tool_name}, user said: {confirm}"
            )

            if confirm in ("yes", "y"):
                tool_name = pending_confirmation["tool_name"]
                tool_args = pending_confirmation.get("tool_args", {})
                matched_tool = next(
                    (t for t in tool_functions if t.name == tool_name), None
                )
                if matched_tool:
                    logger.info(
                        f"[AGENT] User confirmed. Executing tool: {tool_name} with args: {tool_args}"
                    )
                    try:
                        output = matched_tool.invoke(tool_args)
                        messages.append(HumanMessage(content=f"[TOOL OUTPUT] {output}"))
                    except Exception as e:
                        messages.append(HumanMessage(content=f"[TOOL ERROR] {e}"))

                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "tool_args": None},
                }
            else:
                messages.append(
                    HumanMessage(content=f"[SAFEGUARD] Action '{tool_name}' canceled.")
                )
                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "tool_args": None},
                }

    # Lazy load the model chain if not ready
    chain = get_model_chain()

    print("\n[AI]: ", end="", flush=True)
    response = None
    for chunk in chain.stream(messages):
        if response is None:
            response = chunk
        else:
            response += chunk

        if chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")
    logger.info(f"[AGENT] Response finished")

    # Check for dangerous tools in the response
    if response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] in DANGEROUS_TOOLS:
                logger.info(f"[AGENT] Dangerous tool detected: {tc['name']}")
                return {
                    "messages": [
                        response,
                        HumanMessage(
                            content=f"I'm about to perform '{tc['name']}'. This will delete data permanently. Please confirm with 'yes' or 'no'."
                        ),
                    ],
                    "pending_confirmation": {
                        "tool_name": tc["name"],
                        "tool_args": tc["args"],
                    },  # We assume only one dangerous tool at a time
                }

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__", "call_model"]:
    """
    Determine the next node.
    """
    messages = state["messages"]
    last_message = messages[-1]
    pending_confirmation = state.get("pending_confirmation", {})
    logger.info(
        f"""
                [AGENT] Evaluating next step with
                \nlast message type: {type(last_message).__name__} and content: {last_message.content[:100]}
                \npending confirmation: {pending_confirmation}
                \nTools in last message: {getattr(last_message, 'tool_calls', None)}
                \n tool names: {[tc['name'] for tc in getattr(last_message, 'tool_calls', [])] if getattr(last_message, 'tool_calls', None) else None}
                """
    )

    if pending_confirmation and pending_confirmation.get("tool_name"):
        return END

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return END


# -------------------------
# Graph Construction
# -------------------------
graph = StateGraph(AgentState)

graph.add_node("agent", call_model)
graph.add_node("tools", ToolNode(tools=tool_functions))

graph.set_entry_point("agent")

graph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "tools",
        "__end__": END,
        "call_model": "agent",  # Not used currently but good for loops
    },
)

graph.add_edge("tools", "agent")

app = graph.compile()
