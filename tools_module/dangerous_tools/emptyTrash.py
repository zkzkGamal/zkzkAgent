import subprocess, logging
from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def empty_trash() -> str:
    """Empty Trash and log output."""
    logger.info(f"[TOOL] empty_trash called")
    try:
        process = subprocess.Popen(
            "rm -rf ~/.local/share/Trash/*",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
        )

        output_lines = []
        for line in iter(process.stdout.readline, ""):
            if line:
                line = line.strip()
                logger.info(f"[TRASH LOG] {line}")
                output_lines.append(line)

        process.wait()
        return f"Trash emptied successfully. Logs:\n" + "\n".join(output_lines)
    except Exception as e:
        logger.error(f"[TOOL] empty_trash error: {e}")
        return f"Error emptying Trash: {e}"

@tool
def remove_file(path: str) -> str:
    """Remove a file."""
    logger.info(f"[TOOL] remove_file called with path={path}")
    try:
        subprocess.Popen(["rm", "-rf", path])
        logger.info(f"[TOOL] remove_file success for path={path}")
        return f"File {path} removed successfully."
    except Exception as e:
        logger.error(f"[TOOL] remove_file error for path={path}: {e}")
        return f"Error removing file {path}: {e}"
    

