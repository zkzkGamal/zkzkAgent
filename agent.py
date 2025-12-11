import logging
from typing import Literal

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from state import AgentState
from tools import read_file, run_deploy_script, open_vscode, empty_trash, clear_tmp

logger = logging.getLogger(__name__)

# -------------------------
# Initialize Model and Tools
# -------------------------
logger.info("[MODEL INIT] Initializing ChatOllama")
llm = ChatOllama(model="qwen3-vl:4b-instruct-q4_K_M", temperature=0)
tools = [read_file, run_deploy_script, open_vscode, empty_trash, clear_tmp]
llm_with_tools = llm.bind_tools(tools)
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
                # User confirmed. We need to execute the tool.
                # Since we are in 'call_model', we can't easily jump to 'tools' node with the *previous* tool call
                # because the previous tool call was in the AIMessage *before* the confirmation request.
                # Actually, the confirmation request was a HumanMessage added by the agent?
                # No, in the original code, the agent added a HumanMessage asking for confirmation.
                # Here, we should probably have returned an AIMessage asking for confirmation, or just a HumanMessage.

                # Let's look at how we set up the confirmation request below.
                # If we confirmed, we clear the pending state.
                # But we still need to execute the tool.
                # We can manually execute it here or try to trick the graph.
                # Manual execution is safest to replicate original behavior.

                # Find the tool instance
                matched_tool = next((t for t in tools if t.name == tool_name), None)
                if matched_tool:
                    # We need the args. Where did we save them?
                    # The original code didn't save args in pending_confirmation!
                    # It just re-executed handle_tool_call({"name": tool_name, "args": {}}, state)
                    # Wait, the original code passed empty args {} for the dangerous tools?
                    # "state = handle_tool_call({"name": tool_name, "args": {}}, state)"
                    # Yes, empty_trash and clear_tmp take no args.
                    # So it was fine.

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
                # Found a dangerous tool.
                # We should NOT return the tool call in the AIMessage in a way that triggers the 'tools' node immediately
                # OR we should intercept it.

                # If we return the response as is, the 'tools' node (if we use one) will execute it.
                # We need to intercept.

                # Let's modify the response to NOT have tool calls, or handle it manually.
                # Or we can return a special state.

                logger.info(f"[AGENT] Dangerous tool detected: {tc['name']}")

                # We append the AIMessage but STRIP the tool calls so the graph doesn't automatically go to tools?
                # Or we just don't return it yet?

                # Let's append a request for confirmation.
                # We need to save which tool was requested.

                # We can append the original response, but we need to prevent the 'tools' node from running it.
                # We can do this by having a conditional edge that checks for dangerous tools.

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

    # If we are waiting for confirmation, we should stop and wait for user input.
    # But 'call_model' already added the confirmation request message.
    # So we should return END to wait for user input.
    if pending_confirmation and pending_confirmation.get("tool_name"):
        return END

    # If the last message has tool calls, go to tools.
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return END


# -------------------------
# Graph Construction
# -------------------------
graph = StateGraph(AgentState)

graph.add_node("agent", call_model)
graph.add_node("tools", ToolNode(tools))

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
