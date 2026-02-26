from langchain_core.tools import tool
import subprocess , logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def run_command(command: str) -> str:
    """Run a shell command and return the output."""
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        logger.info(f"Command executed successfully: {result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing command: {command}\nError: {e.stderr}")
        return f"Error: {e.stderr}"
