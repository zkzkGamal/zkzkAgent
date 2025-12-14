import logging, os
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from agent import app
from modules.voice_module import VoiceModule

# -------------------------
# Configure logging
# -------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

voice_module = VoiceModule()


# -------------------------
# Main Execution
# -------------------------
def main():
    logger.info("[MAIN] Starting AI assistant")

    # Initial State
    messages = [
        SystemMessage(
            content=f"""
                You are a local AI assistant. When the user requests an action:
                    1. If the user requests a deployment, read the deploy script, choose the numeric option automatically, and run it with real-time logs.
                    2. You can call tools like open_vscode, empty_trash, and clear_tmp when requested.
                    3. Always stream outputs and update state messages.
                    4. For dangerous operations (emptying trash, clearing /tmp), always ask the user to confirm before executing.
                You are running on Ubuntu Linux.
                    The current user's home directory is:
                    {os.path.expanduser("~")}

                    Do NOT guess paths like /home/ubuntu.
                    Always use this home directory.
            """
        )
    ]

    current_state = {
        "messages": messages,
        "pending_confirmation": {"tool_name": None, "user_message": None},
        "running_processes": {},
    }

    logger.info("AI Assistant Ready. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_input = input("Enter your request: ").strip()
            # logger.info("Listening for voice input...")
            # user_input = voice_module()
            # if user_input is None:
            #     logger.info("No valid input detected. Please try again.")
            #     continue
            # logger.info(f"[USER]: {user_input}")
            if user_input.lower() in ["exit", "quit", ""]:
                break

            # Append user message
            current_state["messages"].append(HumanMessage(content=user_input))

            final_state = app.invoke(current_state)

            current_state = final_state

            last_msg = current_state["messages"][-1]
            if isinstance(last_msg, AIMessage):
                logger.info(f"\n[AI]: {last_msg.content}\n")
            elif isinstance(last_msg, HumanMessage):
                logger.info(f"\n[SYSTEM]: {last_msg.content}\n")

        except KeyboardInterrupt:
            logger.info("\nExiting...")
            break
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            break


if __name__ == "__main__":
    main()
