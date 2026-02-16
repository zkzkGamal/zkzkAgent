from tools_module import (
    runDeployScript,
    runCommand,
)

from tools_module.dangerous_tools import emptyTrash, emptyTmp, removeFile
from tools_module.files_tools import (
    findFile,
    readFile,
    openFile,
    findFolder,
    getFileContent,
    getFileInfo,
    writeFile,
    createProjectFolder,
)
from tools_module.processes_tools import findProcess, killProcess
from tools_module.network_tools import checkInternet, enableWifi, duckduckgo_search , duckduckgo_search_images
from tools_module.applications_tools import openVsCode, openBrowser

__all__ = [
    findFile.find_file,
    readFile.read_file,
    openFile.open_file,
    findFolder.find_folder,
    getFileContent.get_file_content,
    getFileInfo.get_files_info,
    writeFile.write_file,
    createProjectFolder.create_project_folder,
    runDeployScript.run_deploy_script,
    runDeployScript.stop_frontend,
    openVsCode.open_vscode,
    openBrowser.open_browser,
    emptyTrash.empty_trash,
    removeFile.remove_file,
    emptyTmp.clear_tmp,
    killProcess.kill_process,
    findProcess.find_process,
    checkInternet.check_internet,
    enableWifi.enable_wifi,
    duckduckgo_search.duckduckgo_search,
    duckduckgo_search_images.duckduckgo_search_images,
    runCommand.run_command,
]
