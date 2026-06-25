from preprocessing.get_clean_history import get_clean_history
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from core.state import AgentState
from core.loadPrompts import LoadPrompts
import logging
from models.LLM import llm
from core.tools import __all__ as tool_functions
from agent_nodes._stream import stream_to_stdout


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_prompts = LoadPrompts()
execution_prompt = load_prompts.load_prompt("executor.yaml")

_model_chain = None


def get_model_chain():
    global _model_chain
    if _model_chain is None:
        logger.info("[MODEL INIT] Lazily binding tools to ChatOllama")
        _model_chain = llm.bind_tools(tool_functions)
        logger.info("[MODEL INIT] Model initialized and tools bound")
    logger.info("[MODEL INIT] Model already initialized")
    return _model_chain


DANGEROUS_TOOLS = [
    "empty_trash",
    "clear_tmp",
    "remove_file",
    "install_package",
    "remove_package",
]


def execute_node(state: AgentState):
    """
    The main agent node.
    It handles:
    1. Checking for pending confirmations.
    2. Invoking the LLM.
    """
    messages = get_clean_history(state)
    messages = [SystemMessage(execution_prompt[0].content), *messages]
    pending_confirmation = state.get(
        "pending_confirmation", {"tool_name": None, "user_message": None}
    )

    logger.info(f"[AGENT] Processing with {len(messages)} messages in context")
    if len(messages) > 1:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            logger.info(
                f"[AGENT] Last message: {last_msg.content[:100]}..."
            )  # First 100 chars

    # 1. Handle Pending Confirmation
    if pending_confirmation and pending_confirmation.get("tool_name"):
        tool_name = pending_confirmation["tool_name"]

        # Search backwards — plan_node may have appended an AI message after the user's "yes"
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )

        if last_human:
            confirm = last_human.content.strip().lower()
            logger.info(
                f"[AGENT] Handling pending confirmation for tool: {tool_name}, user said: {confirm}"
            )

            if confirm in ("yes", "y"):
                tool_name = pending_confirmation["tool_name"]
                tool_args = pending_confirmation.get("tool_args", {})
                matched_tool = next(
                    (t for t in tool_functions if t.name == tool_name), None
                )
                if matched_tool:
                    logger.info(
                        f"[AGENT] User confirmed. Executing tool: {tool_name} with args: {tool_args}"
                    )
                    try:
                        output = matched_tool.invoke(tool_args)
                        messages.append(HumanMessage(content=f"[TOOL OUTPUT] {output}"))
                    except Exception as e:
                        messages.append(HumanMessage(content=f"[TOOL ERROR] {e}"))

                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "tool_args": None},
                }
            else:
                messages.append(
                    HumanMessage(content=f"[SAFEGUARD] Action '{tool_name}' canceled.")
                )
                return {
                    "messages": messages,
                    "pending_confirmation": {"tool_name": None, "tool_args": None},
                }

    # If the user just approved a pending plan, inject it as an explicit
    # instruction so the executor carries it out instead of replanning.
    pending_plan = state.get("pending_plan")
    if pending_plan:
        logger.info("[AGENT] Executing approved plan")
        messages.append(
            HumanMessage(
                content=(
                    "I approve the plan below. Execute it now: call the necessary "
                    "tools, then give me the final answer.\n\n" + pending_plan
                )
            )
        )

    # Lazy load the model chain if not ready
    chain = get_model_chain()

    response = stream_to_stdout(chain.stream(messages))
    logger.info(f"[AGENT] Response finished")

    # Check for dangerous tools in the response
    if response is not None and response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] in DANGEROUS_TOOLS:
                logger.info(f"[AGENT] Dangerous tool detected: {tc['name']}")
                return {
                    "messages": [
                        response,
                        HumanMessage(
                            content=f"I'm about to perform '{tc['name']}'. This will delete data permanently. Please confirm with 'yes' or 'no'."
                        ),
                    ],
                    "pending_confirmation": {
                        "tool_name": tc["name"],
                        "tool_args": tc["args"],
                    },  # We assume only one dangerous tool at a time
                    "pending_plan": None,  # plan (if any) is now being executed
                }

    # The stream produced nothing usable (no text, no tool calls) — emit a
    # visible fallback so the turn is never silent.
    if response is None or (
        not (response.content or "").strip() and not response.tool_calls
    ):
        fallback = "I wasn't able to produce a response for that. Could you rephrase?"
        print(f"\n[AI]: {fallback}\n")
        logger.warning("[AGENT] Empty response — emitted fallback message")
        return {"messages": [AIMessage(content=fallback)], "pending_plan": None}

    return {"messages": [response], "pending_plan": None}
