from typing import Annotated, Sequence, Dict, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing import Literal


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    category: Optional[Literal["DIRECT_EXECUTION", "NEEDS_PLANNING", "CONVERSATIONAL"]]
    pending_confirmation: Optional[Dict[str, Optional[str]]]
    pending_plan: Optional[str]
    running_processes: Optional[Dict[str, int]]
    router_rationale: Optional[str]
    iteration_count: Optional[int]
    exec_backend: Optional[str]  # backend the executor uses for the current task
    interrupted: Optional[Dict]  # {backend, error, handover, can_continue}: a model failure stopped the task
    takeover: Optional[Dict]  # {text, start}: a second model finishes the task from a handover summary
