from langchain_core.messages import HumanMessage, AIMessage

def get_clean_history(state: dict) -> list:
    """
    Returns a filtered list of messages excluding AI and Tool outputs.
    Useful for passing context to a Router or Planner node.
    """
    raw_messages = state.get("messages", [])
    
    # Keep only Human and AI messages
    clean_messages = [
        msg for msg in raw_messages 
        if isinstance(msg, (HumanMessage, AIMessage))
    ]
    
    return clean_messages