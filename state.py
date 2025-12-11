from typing import Annotated, Sequence, List, Dict, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    pending_confirmation: Optional[Dict[str, Optional[str]]]
