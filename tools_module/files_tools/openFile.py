import os
import subprocess
from langchain_core.tools import tool
from models.tts import speak

@tool
def open_file(file_path: str) -> str:
    """
    Opens a file in the default system application.
    Works for text, images, PDFs, or any file type with a default handler.
    """
    file_path = os.path.expanduser(file_path)

    if not os.path.exists(file_path):
        return f"[ERROR] File not found: {file_path}"

    try:
        subprocess.Popen(["xdg-open", file_path])
        speak(f"file opened successfully")
        return f"[SUCCESS] Opened file: {file_path}"
    except Exception as e:
        speak(f"Failed to open file {e}")
        return f"[ERROR] Failed to open file {file_path}: {e}"
