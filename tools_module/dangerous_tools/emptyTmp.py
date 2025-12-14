from langchain_core.tools import tool
import subprocess , logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def clear_tmp() -> str:
    """Clear tmp."""
    logger.info(f"[TOOL] clear_tmp called")
    try:
        process = subprocess.Popen(
            "rm -rf ~/tmp/*",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
        )

        output_lines = []
        for line in iter(process.stdout.readline, ""):
            if line:
                line = line.strip()
                logger.info(f"[TMP LOG] {line}")
                output_lines.append(line)

        process.wait()
        return "Tmp cleared successfully."
    except Exception as e:
        logger.error(f"[TOOL] clear_tmp error: {e}")
        return f"Error clearing tmp: {e}"
