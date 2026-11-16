from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

CONFIRM_TAG = "confirm"  # additional_kwargs["zkzk"] on the agent's "I'm about to…" prompts


def _is_confirm_prompt(message) -> bool:
    return isinstance(message, HumanMessage) and (message.additional_kwargs or {}).get("zkzk") == CONFIRM_TAG


def pair_tool_calls(messages: list) -> list:
    """Put each tool result right after the AI message that asked for it.

    Model APIs reject a tool call without its result, and a confirmation puts
    the user's "yes" between the two. Calls that never ran get "Not run.".
    """
    results = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    paired = []
    for message in messages:
        if isinstance(message, ToolMessage) or _is_confirm_prompt(message):
            continue
        paired.append(message)
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                result = results.pop(call["id"], None)
                paired.append(result if result is not None else ToolMessage(
                    content="Not run.", tool_call_id=call["id"], name=call["name"]
                ))
    return paired


def get_clean_history(state: dict, include_tool_messages: bool = True) -> list:
    """
    Returns a filtered list of messages from the state.

    Args:
        include_tool_messages: If True (default), tool calls and their results
            are kept, paired, so the executor LLM can see tool results. Set to
            False for nodes that only need the human/AI conversation: tool
            calls are reduced to their text, and dropped if they have none.
    """
    raw_messages = state.get("messages", [])

    if include_tool_messages:
        allowed = (HumanMessage, AIMessage, ToolMessage)
        return pair_tool_calls([msg for msg in raw_messages if isinstance(msg, allowed)])

    chat = []
    for msg in raw_messages:
        if isinstance(msg, HumanMessage) and not _is_confirm_prompt(msg):
            chat.append(msg)
        elif isinstance(msg, AIMessage):
            if not msg.tool_calls:
                chat.append(msg)
            elif isinstance(msg.content, str) and msg.content.strip():
                chat.append(AIMessage(content=msg.content))
    return chat
