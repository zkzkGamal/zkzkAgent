import logging, pathlib, re
from typing import Literal
from models.LLM import llm
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from core.state import AgentState
from core.tools import __all__ as tool_functions
from agent_nodes.classify_node import classify_node
from agent_nodes.plan_node import plan_node
from agent_nodes.conversation_node import conversation_node
from agent_nodes.execute_node import execute_node

base_path = pathlib.Path(__file__).parent.parent
logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15  # Maximum tool call cycles before forcing stop


def route_entry(state: AgentState) -> str:
    """Bypass the classifier entirely when a dangerous-tool confirmation is pending."""
    pending = state.get("pending_confirmation", {})
    if pending and pending.get("tool_name"):
        logger.info(
            "[ENTRY ROUTER] Pending confirmation active → routing directly to execute"
        )
        return "execute"
    return "classify"


def route_after_classify(state: AgentState) -> str:
    category = state.get("category", "CONVERSATIONAL")
    logger.info(f"[ROUTER] Routing to: {category}")
    if category == "DIRECT_EXECUTION":
        return "execute"
    elif category == "NEEDS_PLANNING":
        return "plan"
    else:
        return "conversational"


def should_continue(state: AgentState) -> Literal["tools", "__end__", "call_model"]:
    """
    Determine the next node.
    """
    messages = state["messages"]
    last_message = messages[-1]
    pending_confirmation = state.get("pending_confirmation", {})
    iteration_count = state.get("iteration_count", 0)
    logger.info(
        f"""
                [AGENT] Evaluating next step with
                \nlast message type: {type(last_message).__name__} and content: {last_message.content[:100]}
                \npending confirmation: {pending_confirmation}
                \nTools in last message: {getattr(last_message, 'tool_calls', None)}
                \n tool names: {[tc['name'] for tc in getattr(last_message, 'tool_calls', [])] if getattr(last_message, 'tool_calls', None) else None}
                \n iteration: {iteration_count}/{MAX_ITERATIONS}
                """
    )

    if pending_confirmation and pending_confirmation.get("tool_name"):
        return "__end__"

    # Stop if we've exceeded max iterations
    if iteration_count >= MAX_ITERATIONS:
        logger.warning(f"[AGENT] Max iterations ({MAX_ITERATIONS}) reached — forcing stop.")
        return "__end__"

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "__end__"


_tool_node = ToolNode(tools=tool_functions)

def tool_node_with_counter(state: AgentState) -> dict:
    """Run tools and increment the iteration counter."""
    result = _tool_node.invoke(state)
    return {
        **result,
        "iteration_count": state.get("iteration_count", 0) + 1,
    }


graph = StateGraph(AgentState)

graph.add_node("classify", classify_node)
graph.add_node("plan", plan_node)
graph.add_node("conversational", conversation_node)
graph.add_node("execute", execute_node)
graph.add_node("tools", tool_node_with_counter)

graph.add_conditional_edges(
    START,
    route_entry,
    {"execute": "execute", "classify": "classify"},
)

graph.add_conditional_edges(
    "classify",
    route_after_classify,
    {
        "execute": "execute",
        "plan": "plan",
        "conversational": "conversational",
    },
)

graph.add_edge("plan", "execute")

graph.add_conditional_edges(
    "execute",
    should_continue,
    {
        "tools": "tools",
        "__end__": END,
    },
)

graph.add_edge("tools", "execute")
graph.add_edge("conversational", END)

app = graph.compile()

if __name__ == "__main__":
    from IPython.display import Image

    png_bytes = app.get_graph().draw_mermaid_png()

    with open("graph.png", "wb") as f:
        f.write(png_bytes)
