import os
import subprocess
import logging
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from state import AgentState
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

# We need a local LLM instance for the deploy script tool if it uses one internally.
# Ideally, we should pass the LLM or use the one from the agent, but for simplicity
# and to keep tools self-contained or easy to use, we might initialize a small one here
# or rely on the agent passing it.
# The original code used a global 'llm' in 'run_deploy_script'.
# We will instantiate a local one for the tool or refactor to avoid it.
# For now, let's instantiate it inside the tool to be safe, or pass it in.
# Re-instantiating might be slow. Let's try to keep it simple.


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

    # We need an LLM for this tool as per original code
    llm = ChatOllama(model="qwen3-vl:4b-instruct-q4_K_M", temperature=0)

    # 1️⃣ Read the deploy script
    try:
        # We can call the read_file function directly since it's a python function decorated with @tool
        # But @tool makes it a StructuredTool. We can use .invoke or just duplicate logic.
        # Let's use the tool properly.
        script_content = read_file.invoke({"path": deploy_path})
        state["messages"].append(
            HumanMessage(content=f"[SCRIPT CONTENT]\n{script_content}")
        )
    except Exception as e:
        state["messages"].append(
            HumanMessage(content=f"[ERROR] Cannot read deploy script: {e}")
        )
        return state
    logger.info("[TOOL] Deploy script read successfully")

    # 2️⃣ Get the last human instruction
    user_instruction = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage) and not msg.content.startswith(
            "[SCRIPT CONTENT]"
        ):
            user_instruction = msg.content
            break
    if not user_instruction:
        state["messages"].append(
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
    # We shouldn't append this to the main state messages to avoid cluttering the context too much
    # or maybe we should? The original code did.
    state["messages"].append(HumanMessage(content=ai_prompt))
    response = llm.invoke(state["messages"])
    numeric_choice = response.content.strip()
    logger.info(f"[TOOL] AI chose option: {numeric_choice}")
    state["messages"].append(SystemMessage(content=f"[AI CHOICE] {numeric_choice}"))

    # 4️⃣ Run the deploy script
    try:
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
                state["messages"].append(SystemMessage(content=f"[DEPLOY LOG] {line}"))

        process.wait()
    except Exception as e:
        logger.error(f"[TOOL] run_deploy_script error: {e}")
        state["messages"].append(
            SystemMessage(content=f"[ERROR] Deploy script failed: {e}")
        )

    return state


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
            shell=True,
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
            shell=True,
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
