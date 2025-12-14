import subprocess , logging
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
        process = subprocess.Popen(
            ["./deploy_v2.sh", numeric_choice],
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
    except Exception as e:
        logger.error(f"[TOOL] run_deploy_script error: {e}")
        state["messages"].append(
            SystemMessage(content=f"[ERROR] Deploy script failed: {e}")
        )

    return state

