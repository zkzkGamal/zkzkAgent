import subprocess , logging
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def remove_file(path: str) -> str:
    """Remove a file or folder."""
    logger.info(f"[TOOL] remove_file called with path={path}")
    try:
        subprocess.Popen(["rm", "-rf", path])
        logger.info(f"[TOOL] remove_file success for path={path}")
        return f"removed successfully."
    except Exception as e:
        logger.error(f"[TOOL] remove_file error for path={path}: {e}")
        return f"Error removing {path}: {e}"