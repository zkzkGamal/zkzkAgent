from langchain_core.tools import tool
import subprocess , logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def end_main_process(pid: str) -> str:
    """end the main process"""
    try:
        result = subprocess.run("kill -9 " + pid, shell=True, check=True, text=True, capture_output=True)
        logger.info(f"Command executed successfully: {result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing command: {pid}\nError: {e.stderr}")
        return f"Error: {e.stderr}"
