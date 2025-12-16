from langchain_core.tools import tool
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_CHARS = 10000


@tool
def write_file(working_directory: str, file_path: str, content: str) -> str:
    """Write a file with the given content. Limited to 10000 characters. Used for code writing within a working directory."""
    logger.info(
        f"[TOOL] write_file called with working_directory={working_directory}, file_path={file_path}"
    )
    abs_working_dir = os.path.abspath(working_directory)
    abs_file_path = os.path.abspath(os.path.join(working_directory, file_path))

    if not abs_file_path.startswith(abs_working_dir):
        return f'Error: Cannot write to "{file_path}" as it is outside the permitted working directory'
    parent_dir = os.path.dirname(abs_file_path)
    if not os.path.isdir(parent_dir):
        try:
            os.makedirs(parent_dir, exist_ok=True)
        except OSError as e:
            return f"Couldn't create parent directories: {e}"
    if not os.path.isfile(abs_file_path):
        pass
    try:
        with open(abs_file_path, "w") as file:
            file.write(content)
        return (
            f'Successfully wrote to "{file_path}" ({len(content)} characters written)'
        )
    except Exception as e:
        return f"Failed to write to file: {e}"
