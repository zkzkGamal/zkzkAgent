import os
import subprocess
import logging
from typing import Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

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
# class AgentState(dict):
#     messages: Annotated[Sequence[BaseMessage], add_messages]
from pydantic import BaseModel
from typing import List , Dict
from langchain_core.messages import BaseMessage


class AgentState(BaseModel):
    messages: List[BaseMessage]
    pending_confirmation: Dict = {"tool_name": None, "user_message": None}


# -------------------------
# 2️⃣ Define Tools
# -------------------------
@tool
def read_file(path: str) -> str:
    """Read a file and return its content."""
    logger.info(f"[TOOL] read_file called with path={path}")
    try:
        with open(path, "r") as f:
            content = f.read()
        logger.info(f"[TOOL] read_file success, {len(content)} chars")
        return content
    except Exception as e:
        logger.error(f"[TOOL] read_file error: {e}")
        return f"Error reading file {path}: {e}"


@tool
def run_deploy_script(state: AgentState) -> AgentState:
    """Fully automated deployment: AI reads script and chooses the correct option."""
    deploy_path = "../deploy/deploy_v2.sh"

    # 1️⃣ Read the deploy script
    try:
        script_content = read_file.run({"path": deploy_path})
        state.messages.append(
            HumanMessage(content=f"[SCRIPT CONTENT]\n{script_content}")
        )
    except Exception as e:
        state.messages.append(
            HumanMessage(content=f"[ERROR] Cannot read deploy script: {e}")
        )
        return state
    logger.info("[TOOL] Deploy script read successfully")

    # 2️⃣ Get the last human instruction
    user_instruction = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage) and not msg.content.startswith(
            "[SCRIPT CONTENT]"
        ):
            user_instruction = msg.content
            break
    if not user_instruction:
        state.messages.append(
            HumanMessage(content="[ERROR] No user instruction found.")
        )
        return state

    # 3️⃣ Ask AI to pick numeric option
    ai_prompt = f"""
Based on the deploy script and user instruction, return only the numeric option (1, 2, or 3)
that should be passed to the deploy script.

User instruction:
{user_instruction}

Deploy script content:
{script_content}
"""
    state.messages.append(HumanMessage(content=ai_prompt))
    response = llm.invoke(state.messages)
    numeric_choice = response.content.strip()
    logger.info(f"[TOOL] AI chose option: {numeric_choice}")
    state.messages.append(SystemMessage(content=f"[AI CHOICE] {numeric_choice}"))

    # 4️⃣ Run the deploy script
    process = subprocess.Popen(
        ["./deploy_v2.sh", numeric_choice],
        cwd="../deploy",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # 5️⃣ Stream logs in real-time
    for line in iter(process.stdout.readline, ""):
        if line:
            line = line.strip()
            print(line)
            state.messages.append(SystemMessage(content=f"[DEPLOY LOG] {line}"))

    process.wait()
    return state


@tool
def confirm_action(action_name: str, user_message: str) -> bool:
    """
    Ask the user to confirm before executing dangerous actions.
    Returns True if confirmed, False otherwise.
    """
    print(f"[CONFIRMATION] User requested: '{user_message}'")
    response = (
        input(f"Are you sure you want to perform '{action_name}'? (yes/no): ")
        .strip()
        .lower()
    )
    return response in ("yes", "y")


@tool
def open_vscode(path: str) -> str:
    """Open VSCode."""
    logger.info(f"[TOOL] open_vscode called")
    try:
        subprocess.Popen(["code", "." if not path or path.strip() == "" else path])
        logger.info(f"[TOOL] open_vscode success")
        return "VSCode opened successfully."
    except Exception as e:
        logger.error(f"[TOOL] open_vscode error: {e}")
        return f"Error opening VSCode: {e}"


@tool
def empty_trash() -> str:
    """Empty Trash and log output."""
    logger.info(f"[TOOL] empty_trash called")
    try:
        process = subprocess.Popen(
            "rm -rf ~/.local/share/Trash/*",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,  # Important for ~ expansion
        )

        output_lines = []
        for line in iter(process.stdout.readline, ""):
            if line:
                line = line.strip()
                logger.info(f"[TRASH LOG] {line}")
                output_lines.append(line)

        process.wait()
        return f"Trash emptied successfully. Logs:\n" + "\n".join(output_lines)
    except Exception as e:
        logger.error(f"[TOOL] empty_trash error: {e}")
        return f"Error emptying Trash: {e}"


@tool
def clear_tmp() -> str:
    """Clear tmp."""
    logger.info(f"[TOOL] clear_tmp called")
    try:
        process = subprocess.Popen(
            "rm -rf ~/tmp/*",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,  # Important for ~ expansion
        )

        output_lines = []
        for line in iter(process.stdout.readline, ""):
            if line:
                line = line.strip()
                logger.info(f"[TMP LOG] {line}")
                output_lines.append(line)

        process.wait()
        return "Tmp cleared successfully."
    except Exception as e:
        logger.error(f"[TOOL] clear_tmp error: {e}")
        return f"Error clearing tmp: {e}"


# -------------------------
# 3️⃣ Handle Tool Calls
# -------------------------
DANGEROUS_TOOLS = ["empty_trash", "clear_tmp"]

def handle_tool_call(tool_call, state: AgentState):
    name = tool_call["name"]
    args = tool_call.get("args", {})

    # Safeguard: Check pending confirmation
    if name in DANGEROUS_TOOLS and not getattr(state, "pending_confirmation", None):
        user_msg = ""
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg.content
                break
        state.pending_confirmation = {"tool_name": name, "user_message": user_msg}
        state.messages.append(HumanMessage(
            content=f"I'm about to perform '{name}'. This will delete data permanently. Please confirm with 'yes' or 'no'."
        ))
        return state

    # Execute tool if confirmed or not dangerous
    matched_tool = next((t for t in tools if t.name == name), None)
    if not matched_tool:
        state.messages.append(HumanMessage(content=f"[ERROR] Tool {name} not found."))
        return state

    tool_input = {"state": state} if name == "run_deploy_script" else args
    output = matched_tool.run(tool_input)

    if isinstance(output, AgentState):
        state = output
    else:
        state.messages.append(HumanMessage(content=f"[TOOL OUTPUT] {output}"))

    next_calls = getattr(output, "tool_calls", [])
    for nc in next_calls:
        state = handle_tool_call(nc, state)

    return state
# -------------------------
# 4️⃣ Initialize Model
# -------------------------
logger.info("[MODEL INIT] Initializing ChatOllama")
llm = ChatOllama(model="qwen3-vl:4b-instruct-q4_K_M", temperature=0)
tools = [read_file, run_deploy_script, open_vscode, empty_trash, clear_tmp]
llm = llm.bind_tools(tools)
logger.info("[MODEL INIT] Model initialized and tools bound")


# -------------------------
# 5️⃣ Agent Function
# -------------------------
# def call_model(state: AgentState) -> AgentState:
#     logger.info("[AGENT] Invoking model with current messages")
#     response = llm.invoke(state.messages)
#     logger.info(f"[MODEL RESPONSE] {response.content}")
#     state.messages.append(response)

#     # Handle tool calls
#     tool_calls = getattr(response, "tool_calls", [])
#     if tool_calls:
#         logger.info(f"[MODEL TOOL_CALLS] {tool_calls}")
#     for tc in tool_calls:
#         state = handle_tool_call(tc, state)

#     return state

def call_model(state: AgentState) -> AgentState:
    # Handle pending confirmation first
    tool_name = state.pending_confirmation["tool_name"]
    if tool_name:
        confirm = state.messages[-1].content.strip().lower()
        logger.info(f"[AGENT] Handling pending confirmation for tool: {tool_name}")
        tool_name = state.pending_confirmation["tool_name"]
        if confirm in ("yes", "y"):
            state.pending_confirmation = None
            state = handle_tool_call({"name": tool_name, "args": {}}, state)
        else:
            state.messages.append(HumanMessage(content=f"[SAFEGUARD] Action '{tool_name}' canceled."))
            state.pending_confirmation = None
        return state

    # Normal AI invocation
    response = llm.invoke(state.messages)
    logger.info(f"[MODEL RESPONSE] {response.content}")
    state.messages.append(response)

    tool_calls = getattr(response, "tool_calls", [])
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


def call_action(content):
    initial_state = AgentState(
        messages = [
            SystemMessage(
                content="""
                            You are a local AI assistant. When the user requests an action:
                                1. If the user requests a deployment, read the deploy script, choose the numeric option automatically, and run it with real-time logs.
                                2. You can call tools like open_vscode, empty_trash, and clear_tmp when requested.
                                3. Always stream outputs and update state messages.
                                4. For dangerous operations (emptying trash, clearing /tmp), always ask the user to confirm before executing.

                        """
            ),
            HumanMessage(content=content),
        ],
    )

    final_state = app.invoke(initial_state)

    logger.info("[MAIN] Final State Messages:")
    logger.info("===================================")
    for msg in final_state["messages"]:
        logger.info(f"{msg.__class__.__name__}: {msg.content}")


# -------------------------
# 7️⃣ Run Assistant
# -------------------------
if __name__ == "__main__":
    logger.info("[MAIN] Starting AI assistant")
    content = input("Enter your request: ")

    while content.strip().lower() != "exit" or content.strip().lower() != "quit":
        call_action(content)
        content = input("Enter your request: ")
