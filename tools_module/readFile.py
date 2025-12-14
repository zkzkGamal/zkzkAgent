from langchain_core.tools import tool
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def read_file(path: str) -> str:
    """Read a file and return its content."""
    logger.info(f"[TOOL] read_file called with path={path}")
    try:
        with open(path, "r") as f:
            content = f.read()
        logger.info(f"[TOOL] read_file success, {len(content)} chars")
        return content
    except Exception as e:
        logger.error(f"[TOOL] read_file error: {e}")
        return f"Error reading file {path}: {e}"
