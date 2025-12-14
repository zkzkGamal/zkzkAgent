from langchain_core.tools import tool
import logging
import subprocess
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def find_folder(folder_name: str, search_path: str = "~/") -> str:
    """Search for a folder in the given directory and its subdirectories."""
    search_path = os.path.expanduser(search_path)

    logger.info(
        f"[TOOL] find_folder called with folder_name={folder_name}, search_path={search_path}"
    )

    try:
        result = subprocess.run(
            ["find", search_path, "-type", "d", "-name", folder_name],
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout.strip()
        if output:
            logger.info(f"[TOOL] find_folder found:\n{output}")
            return output

        return f"No folders found matching {folder_name} in {search_path}"

    except subprocess.CalledProcessError as e:
        logger.error(f"[TOOL] find_folder error: {e.stderr}")
        return f"Error searching for folder {folder_name}: {e.stderr}"
