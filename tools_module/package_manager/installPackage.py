from langchain_core.tools import tool
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def install_package(installation_command: str) -> str:
    """Install system package using the provided installation command."""
    logger.info(f"Installing package with command: {installation_command}")
    try:
        result = subprocess.run(
            installation_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        logger.info(f"Installation output: {result.stdout}")
        return f"Package installed successfully:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install package: {e.stderr}")
        return f"Failed to install package:\n{e.stderr}"