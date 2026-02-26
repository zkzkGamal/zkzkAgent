from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


def get_clean_history(state: dict, include_tool_messages: bool = True) -> list:
    """
    Returns a filtered list of messages from the state.

    Args:
        include_tool_messages: If True (default), ToolMessages are included so
            the executor LLM can see tool results. Set to False for router/planner
            nodes that only need the human/AI conversation flow.
    """
    raw_messages = state.get("messages", [])

    if include_tool_messages:
        # Keep Human, AI, and Tool messages — full context for the executor
        allowed = (HumanMessage, AIMessage, ToolMessage)
    else:
        # Strip tool results — lighter context for router/planner
        allowed = (HumanMessage, AIMessage)

    return [msg for msg in raw_messages if isinstance(msg, allowed)]
