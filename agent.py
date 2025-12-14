import logging
from typing import Literal
from models.LLM import llm
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from state import AgentState
from tools import __all__ as tool_functions

logger = logging.getLogger(__name__)

# -------------------------
# Initialize Model and Tools
# -------------------------
logger.info("[MODEL INIT] Initializing ChatOllama")
llm_with_tools = llm.bind_tools(tool_functions)
logger.info("[MODEL INIT] Model initialized and tools bound")

DANGEROUS_TOOLS = ["empty_trash", "clear_tmp"]

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
                matched_tool = next((t for t in tool_functions if t.name == tool_name), None)
                if matched_tool:
                    logger.info(f"[AGENT] User confirmed. Executing tool: {tool_name}")
                    try:
                        output = matched_tool.invoke(
                            {}
                        )  # Dangerous tools have no args in this agent
                        messages.append(HumanMessage(content=f"[TOOL OUTPUT] {output}"))
                    except Exception as e:
                        messages.append(HumanMessage(content=f"[TOOL ERROR] {e}"))

                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "user_message": None},
                }
            else:
                messages.append(
                    HumanMessage(content=f"[SAFEGUARD] Action '{tool_name}' canceled.")
                )
                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "user_message": None},
                }

    # 2. Normal AI Invocation
    response = llm_with_tools.invoke(messages)
    logger.info(f"[MODEL RESPONSE] {response.content}")

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
                        "user_message": None,
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
