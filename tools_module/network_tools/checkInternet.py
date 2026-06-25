import urllib.request
import urllib.error
import socket
import logging
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Captive-portal style endpoints that return an empty 204 when online.
# We try a few so one blocked host doesn't produce a false "Disconnected".
CHECK_URLS = (
    "http://www.gstatic.com/generate_204",
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://cp.cloudflare.com/",
)


@tool
def check_internet() -> str:
    """Checks if the internet is accessible by making a quick HTTP request."""
    last_error: Exception | None = None
    for url in CHECK_URLS:
        try:
            urllib.request.urlopen(url, timeout=3)
            logger.info("[TOOL] Internet check: Connected")
            return "Connected"
        except urllib.error.HTTPError as e:
            logger.info(f"[TOOL] Internet check: Connected (server responded {e.code})")
            return "Connected"
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            last_error = e
            continue

    logger.warning(f"[TOOL] Internet check: Disconnected ({last_error})")
    return "Disconnected"
