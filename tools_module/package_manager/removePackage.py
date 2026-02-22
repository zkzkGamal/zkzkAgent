from langchain_core.tools import tool
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def remove_package(remove_command: str) -> str:
    """Remove system package using the provided remove command."""
    logger.info(f"Removing package with command: {remove_command}")
    try:
        result = subprocess.run(
            remove_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logger.info(f"Removal output: {result.stdout}")
        return f"Package removed successfully:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to remove package: {e.stderr}")
        return f"Failed to remove package:\n{e.stderr}"