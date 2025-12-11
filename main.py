import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from agent import app

# -------------------------
# Configure logging
# -------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# -------------------------
# Main Execution
# -------------------------
def main():
    logger.info("[MAIN] Starting AI assistant")

    # Initial State
    messages = [
        SystemMessage(
            content="""
You are a local AI assistant. When the user requests an action:
1. If the user requests a deployment, read the deploy script, choose the numeric option automatically, and run it with real-time logs.
2. You can call tools like open_vscode, empty_trash, and clear_tmp when requested.
3. Always stream outputs and update state messages.
4. For dangerous operations (emptying trash, clearing /tmp), always ask the user to confirm before executing.
"""
        )
    ]

    # We need to maintain the state across turns
    # LangGraph 'app.invoke' returns the final state.
    # We can pass the full state back in.

    current_state = {
        "messages": messages,
        "pending_confirmation": {"tool_name": None, "user_message": None},
    }

    print("AI Assistant Ready. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_input = input("Enter your request: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                break

            # Append user message
            current_state["messages"].append(HumanMessage(content=user_input))

            # Invoke Agent
            # Note: app.invoke returns the final state
            final_state = app.invoke(current_state)

            # Update current state for next turn
            current_state = final_state

            # Print AI Response (last message)
            last_msg = current_state["messages"][-1]
            if isinstance(last_msg, AIMessage):
                print(f"\n[AI]: {last_msg.content}\n")
            elif isinstance(last_msg, HumanMessage):
                # This might happen if we asked for confirmation
                print(f"\n[SYSTEM]: {last_msg.content}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            break


if __name__ == "__main__":
    main()
