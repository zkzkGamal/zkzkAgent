import subprocess
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def check_internet() -> str:
    """Checks if the internet is accessible by pinging a reliable host."""
    try:
        # Ping 8.8.8.8 once with a 2-second timeout
        subprocess.check_call(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("[TOOL] Internet check: Connected")
        return "Connected"
    except subprocess.CalledProcessError:
        logger.warning("[TOOL] Internet check: Disconnected")
        return "Disconnected"
    except Exception as e:
        logger.error(f"[TOOL] Internet check error: {e}")
        return f"Error checking internet: {e}"


@tool
def enable_wifi() -> str:
    """Enables Wi-Fi using nmcli."""
    try:
        subprocess.check_call(["nmcli", "radio", "wifi", "on"])
        logger.info("[TOOL] Wi-Fi enabled successfully")
        return "Wi-Fi enabled successfully. Please wait a moment for connection."
    except FileNotFoundError:
        return "Error: nmcli not found. Cannot manage Wi-Fi."
    except subprocess.CalledProcessError as e:
        logger.error(f"[TOOL] Failed to enable Wi-Fi: {e}")
        return f"Failed to enable Wi-Fi: {e}"
    except Exception as e:
        logger.error(f"[TOOL] Enable Wi-Fi error: {e}")
        return f"Error enabling Wi-Fi: {e}"
