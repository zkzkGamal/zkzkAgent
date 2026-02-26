import urllib.request
import logging
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def check_internet() -> str:
    """Checks if the internet is accessible by making a quick HTTP request."""
    try:
        # Use a fast DNS server IP to avoid relying on DNS resolution for the check
        urllib.request.urlopen("http://1.1.1.1", timeout=2)
        logger.info("[TOOL] Internet check: Connected")
        return "Connected"
    except Exception as e:
        logger.warning(f"[TOOL] Internet check: Disconnected ({e})")
        return "Disconnected"
