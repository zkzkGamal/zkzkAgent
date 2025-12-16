from langchain_core.tools import tool
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def get_files_info(working_directory: str, directory: str = ".") -> str:
    """Get information about files in a directory. Lists files with size and type within a working directory."""
    logger.info(
        f"[TOOL] get_files_info called with working_directory={working_directory}, directory={directory}"
    )
    abs_working_dir = os.path.abspath(working_directory)
    abs_directory = os.path.abspath(os.path.join(working_directory, directory))

    if not abs_directory.startswith(abs_working_dir):
        return f"Error: {directory} is not a subdirectory of {working_directory}"

    final_response = ""
    contents = os.listdir(abs_directory)
    for content in contents:
        content_path = os.path.join(abs_directory, content)
        is_dir = os.path.isdir(content_path)
        size = os.path.getsize(content_path)
        final_response += f"- {content}: file_size={size} in bytes, is_dir={is_dir}\n"

    return final_response
