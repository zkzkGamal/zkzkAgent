from langchain_core.tools import tool
import logging
import subprocess
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@tool
def find_file(filename: str, search_path: str = "~/") -> str:
    """Search for a file in the given directory and its subdirectories."""
    search_path = os.path.expanduser(search_path)

    logger.info(
        f"[TOOL] find_file called with filename={filename}, search_path={search_path}"
    )

    try:
        result = subprocess.run(
            ["find", search_path, "-name", filename],
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout.strip()
        if output:
            logger.info(f"[TOOL] find_file found:\n{output}")
            return output

        return f"No files found matching {filename} in {search_path}"

    except subprocess.CalledProcessError as e:
        logger.error(f"[TOOL] find_file error: {e.stderr}")
        return f"Error searching for file {filename}: {e.stderr}"

    
if __name__ == "__main__":
    # Example usage
    result = find_file.invoke({"filename": "faroos*", "search_path": "~/Downloads"})
