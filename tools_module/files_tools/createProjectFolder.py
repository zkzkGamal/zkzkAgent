from langchain_core.tools import tool
import os , subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@tool
def create_project_folder(working_directory: str, project_name: str) -> str:
    """Create a new project folder within the working directory. Used when user wants to create a new project."""
    logger.info(
        f"[TOOL] create_project_folder called with working_directory={working_directory}, project_name={project_name}"
    )
    abs_working_dir = os.path.abspath(working_directory)
    abs_project_path = os.path.abspath(os.path.join(working_directory, project_name))

    # Security check: ensure project path is within working directory
    if not abs_project_path.startswith(abs_working_dir):
        return f'Error: Cannot create project "{project_name}" outside the permitted working directory'

    # Check if project already exists
    if os.path.exists(abs_project_path):
        return f'Error: Project folder "{project_name}" already exists at {abs_project_path}'

    try:
        res = subprocess.run(f"mkdir -p {abs_project_path}", shell=True, check=True)
        if res.returncode != 0:
            return f"Failed to create project folder: {res.stderr.decode('utf-8')}"
        logger.info(f"[TOOL] Successfully created project folder: {abs_project_path}")
        return f'Successfully created project folder "{project_name}" at {abs_project_path}'
    except OSError as e:
        logger.error(f"[TOOL] Failed to create project folder: {e}")
        return f"Failed to create project folder: {e}"
    except Exception as e:
        logger.error(f"[TOOL] Unexpected error creating project folder: {e}")
        return f"Unexpected error: {e}"
