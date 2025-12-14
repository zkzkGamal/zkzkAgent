from langchain_core.tools import tool
import logging , subprocess
from state import AgentState
from langchain_core.messages import SystemMessage
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def open_file(state: AgentState, file_path: str) -> AgentState:
    """Opens a file in the default text editor."""
    try:
        subprocess.Popen(["open", file_path])
        logger.info(f"[TOOL] Opened file: {file_path}")
        state["messages"].append(SystemMessage(content=f"[SUCCESS] Opened file: {file_path}"))
    except Exception as e:
        logger.error(f"[TOOL] Failed to open file {file_path}: {e}")
        state["messages"].append(SystemMessage(content=f"[ERROR] Failed to open file {file_path}: {e}"))
    return state
