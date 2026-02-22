from langchain_core.tools import tool
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def detect_operating_system() -> str:
    """Detect the operating system."""
    try:
        result = subprocess.run(
            ["uname", "-s"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return f"Detected OS: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to detect OS: {e}")
        return f"Failed to detect OS: {e.stderr}"