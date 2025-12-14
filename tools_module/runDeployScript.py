import subprocess, logging
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from state import AgentState
from models.LLM import llm
from .readFile import read_file

logger = logging.getLogger(__name__)


@tool
def run_deploy_script(state: AgentState) -> AgentState:
    """Fully automated deployment: AI reads script and chooses the correct option."""
    deploy_path = "../deploy/deploy_v2.sh"
    try:
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

    state["messages"].append(HumanMessage(content=ai_prompt))
    response = llm.invoke(state["messages"])

    numeric_choice = response.content.strip()
    logger.info(f"[TOOL] AI chose option: {numeric_choice}")

    state["messages"].append(SystemMessage(content=f"[AI CHOICE] {numeric_choice}"))

    try:
        log_file = open("../deploy/deploy.log", "w")
        process = subprocess.Popen(
            ["./deploy_v2.sh", numeric_choice],
            cwd="../deploy",
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Store PID in state
        if "running_processes" not in state:
            state["running_processes"] = {}

        state["running_processes"]["deploy_script"] = process.pid

        logger.info(
            f"[TOOL] Deploy script started in background with PID: {process.pid}"
        )
        state["messages"].append(
            SystemMessage(
                content=f"[DEPLOY STARTED] Script running in background. PID: {process.pid}. Logs are being written to deploy.log."
            )
        )

    except Exception as e:
        logger.error(f"[TOOL] run_deploy_script error: {e}")
        state["messages"].append(
            SystemMessage(content=f"[ERROR] Deploy script failed to start: {e}")
        )

    return state
