import subprocess , logging
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def open_vscode(path: str) -> str:
    """Open VSCode."""
    logger.info(f"[TOOL] open_vscode called")
    try:
        subprocess.Popen(["code", "." if not path or path.strip() == "" else path])
        logger.info(f"[TOOL] open_vscode success")
        return "VSCode opened successfully."
    except Exception as e:
        logger.error(f"[TOOL] open_vscode error: {e}")
        return f"Error opening VSCode: {e}"