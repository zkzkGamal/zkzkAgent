import subprocess
import logging
from typing import Dict, TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

from typing_extensions import TypedDict

# -------------------------
# 0️⃣ Configure logging
# -------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# -------------------------
# 1️⃣ Define Agent State
# -------------------------
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# -------------------------
# 2️⃣ Define Tools
# -------------------------
@tool
def read_file(path: str) -> str:
    """Reads a file and returns its content"""
    logger.info(f"[TOOL] read_file called with path={path}")
    try:
        with open(path, "r") as f:
            content = f.read()
        logger.info(f"[TOOL] read_file success, {len(content)} characters read")
        return content
    except Exception as e:
        logger.error(f"[TOOL] read_file error: {e}")
        return f"Error reading file {path}: {e}"


# @tool
# def run_deploy_script(choice: str, state: AgentState) -> AgentState:
#     """Read deploy.sh and run it with the given choice."""
#     deploy_path = "../deploy/deploy.sh"

#     # 1️⃣ Read the file first
#     try:
#         with open(deploy_path, "r") as f:
#             content = f.read()
#         state["messages"].append(HumanMessage(content=f"[SCRIPT CONTENT]\n{content}"))
#     except Exception as e:
#         state["messages"].append(HumanMessage(content=f"[ERROR] Cannot read deploy script: {e}"))
#         return state

#     # 2️⃣ Run the script with choice argument
#     process = subprocess.Popen(
#         ["./deploy_v2.sh", choice],
#         cwd="../deploy",
#         stdout=subprocess.PIPE,
#         stderr=subprocess.STDOUT,
#         text=True,
#     )

#     # 3️⃣ Stream logs and let AI react
#     for line in iter(process.stdout.readline, ""):
#         if line:
#             line = line.strip()
#             print(line)  # terminal output

#             # Append logs as SystemMessage, not HumanMessage
#             state["messages"].append(SystemMessage(content=f"[DEPLOY LOG] {line}"))

#     # Only invoke AI once after deployment is finished (or on actual user prompts)
#     response = llm.invoke(state["messages"])
#     state["messages"].append(response)

#     process.wait()
#     return state

@tool
def run_deploy_script(choice: str, state: AgentState) -> AgentState:
    """Read deploy.sh first, then run it."""
    deploy_path = "../deploy/deploy_v2.sh"

    # Always read the file first
    try:
        # content = read_file(deploy_path)  # call the read_file tool
        content = read_file.run({"path": deploy_path})
        state["messages"].append(HumanMessage(content=f"[SCRIPT CONTENT]\n{content}"))
    except Exception as e:
        state["messages"].append(HumanMessage(content=f"[ERROR] Cannot read deploy script: {e}"))
        return state
    logger.info("[TOOL] deploy script read successfully")
    logger.info(f"[TOOL] Running deploy script with choice={choice}")
    # Then run the script
    process = subprocess.Popen(
        ["./deploy_v2.sh", choice],
        cwd="../deploy",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in iter(process.stdout.readline, ""):
        if line:
            line = line.strip()
            print(line)
            state["messages"].append(SystemMessage(content=f"[DEPLOY LOG] {line}"))

    process.wait()
    return state


# -------------------------
# 3️⃣ Handle tool calls recursively
# -------------------------
def handle_tool_call(tool_call, state: AgentState):
    name = tool_call["name"]
    args = tool_call.get("args", {})
    for t in tools:
        if t.name == name:
            # StructuredTool expects a dict
            tool_input = {"choice": args.get("choice", "1"), "state": state} if name == "run_deploy_script" else args
            output = t.run(tool_input)

            if isinstance(output, dict) and "messages" in output:
                state = output
            else:
                state["messages"].append(HumanMessage(content=f"[TOOL OUTPUT] {output}"))

            # Check for nested tool calls
            next_calls = getattr(output, "tool_calls", [])
            for nc in next_calls:
                state = handle_tool_call(nc, state)
    return state

# -------------------------
# 4️⃣ Initialize model & bind tools
# -------------------------
logger.info("[MODEL INIT] Initializing ChatOllama")
llm = ChatOllama(model="qwen3-vl:4b-instruct-q4_K_M", temperature=0)
tools = [read_file, run_deploy_script]
llm = llm.bind_tools(tools)
logger.info("[MODEL INIT] Model initialized and tools bound")


# -------------------------
# 5️⃣ Agent function
# -------------------------
def call_model(state: AgentState) -> AgentState:
    logger.info("[AGENT] Invoking model with current messages")
    response = llm.invoke(state["messages"])
    logger.info(f"[MODEL RESPONSE] {response.content}")
    state["messages"].append(response)

    tool_calls = getattr(response, "tool_calls", [])
    if tool_calls:
        logger.info(f"[MODEL TOOL_CALLS] {tool_calls}")
    for tc in tool_calls:
        state = handle_tool_call(tc, state)

    return state


# -------------------------
# 6️⃣ Graph
# -------------------------
graph = StateGraph(AgentState)
graph.add_node("our_agent", call_model)
graph.set_entry_point("our_agent")
graph.add_edge("our_agent", END)
app = graph.compile()

# -------------------------
# 7️⃣ Run assistant
# -------------------------
if __name__ == "__main__":
    logger.info("[MAIN] Starting AI assistant")
    initial_state: AgentState = {
        "messages": [
            SystemMessage(
                content="""
You are a local AI assistant. When the user requests a deployment:
1. First, read the deploy script located at ../deploy/deploy.sh to understand available options.
2. Then, run the deploy script using subprocess.
3. Feed the server choice automatically based on user instructions (e.g., backend, frontend, AI).
4. Stream logs back in real-time so you can react and handle next steps.
5. Only call tools when necessary, and make sure the workflow is fully automated.
"""
            ),
            HumanMessage(content="Deploy the backend server."),
        ],
    }

    final_state = app.invoke(initial_state)

    logger.info("[MAIN] Final State Messages:")
    for msg in final_state["messages"]:
        logger.info(f"{msg.__class__.__name__}: {msg.content}")
