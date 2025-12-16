from langchain_core.tools import tool
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_CHARS = 10000


@tool
def get_file_content(working_directory: str, file_path: str) -> str:
    """Read a file and return its content. Limited to 10000 characters. Used for code reading within a working directory."""
    logger.info(
        f"[TOOL] get_file_content called with working_directory={working_directory}, file_path={file_path}"
    )
    abs_working_dir = os.path.abspath(working_directory)
    abs_file_path = os.path.abspath(os.path.join(working_directory, file_path))

    if not abs_file_path.startswith(abs_working_dir):
        return f"Error: {file_path} is not a subdirectory of {working_directory}"

    try:
        with open(abs_file_path, "r") as file:
            content = file.read(MAX_CHARS)
            if len(content) >= MAX_CHARS:
                content += (
                    f'\n[...File "{file_path}" truncated at {MAX_CHARS} characters]'
                )
            return content
    except FileNotFoundError:
        return f"Error: {file_path} not found"
    except Exception as e:
        return f"Error: {e}"
