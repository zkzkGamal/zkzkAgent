import os, sys, pexpect, logging, pathlib, environ , json , re , subprocess
from langchain_core.tools import tool
from models.LLM import llm

base_dir = pathlib.Path(__file__).parent.parent
env = environ.Env()
environ.Env.read_env(base_dir / ".env")

logger = logging.getLogger(__name__)
GPG_PASSWORD = os.getenv("GPG_PASSWORD", "")
SSH_FRONTEND = os.getenv("SSH_FRONTEND", "")
FRONTEND_PORT = os.getenv("FRONTEND_PORT", "")

running_processes = {}


@tool
def run_deploy_script(user_instruction: str):
    """
    Fully autonomous AI deployment.
    user_instruction: e.g. "deploy backend application"
    """
    deploy_path = "../deploy/deploy_v3.sh"

    try:
        env_vars = os.environ.copy()
        env_vars["GPG_PASSWORD"] = GPG_PASSWORD

        child = pexpect.spawn(f"bash {deploy_path}", env=env_vars, encoding="utf-8", timeout=900)
        child.logfile_read = sys.stdout

        # === First prompt: server choice ===
        child.expect("Enter your choice")
        prompt_text = child.before.strip() + "\n" + child.after.strip()
        ai_prompt = f"""
        User instruction: {user_instruction}
        Script prompt/output:
        {prompt_text}
        Return a JSON object in this format:
        {{
            "remote_choice": "1/2/3",
            "server_choice": "1-7 or null if not applicable"
        }}
        Only return valid JSON.
        """
        response = llm.invoke([{"role": "user", "content": ai_prompt}]).content.strip()

        try:
            choices = json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"[AI JSON ERROR] Could not parse JSON: {response}")
            return f"[ERROR] AI returned invalid JSON: {response}"

        # Send server choice
        remote_choice = choices.get("remote_choice")
        server_choice = choices.get("server_choice")
        logger.info(f"[AI SERVER CHOICE] Sending: {remote_choice}")
        child.sendline(str(remote_choice))

        # Send backend choice if applicable
        if server_choice is not None or server_choice != "none":
            child.expect("Enter backend choice")
            logger.info(f"[AI BACKEND CHOICE] Sending: {server_choice}")
            child.sendline(str(server_choice))

        
        # Handle frontend separately: run in background
        if remote_choice == "2":  # frontend
            # Wait until SSH session ends
            child.expect(pexpect.EOF, timeout=10)
            output = child.before.strip()

            # Use regex to find PID
            match = re.search(r"Frontend PID:\s*(\d+)", output)
            if match:
                pid = int(match.group(1))
                running_processes["frontend"] = pid
                logger.info(f"[FRONTEND RUNNING] PID: {pid}")
            else:
                logger.error(f"[FRONTEND ERROR] Could not find PID in output:\n{output}")
                return "[ERROR] Could not retrieve frontend PID"

            # Close pexpect handle without killing process
            child.close(force=True)

            return f"[DEPLOY COMPLETED] Frontend started, PID: {pid}"

        # Wait for script to finish
        child.expect(pexpect.EOF)
        child.close()

        if child.exitstatus != 0:
            logger.error(f"[DEPLOY ERROR] Exit code: {child.exitstatus}")
            return f"[ERROR] Deploy script failed, exit code {child.exitstatus}"

        logger.info("[DEPLOY COMPLETED] Script finished successfully")
        return "[DEPLOY COMPLETED] Script finished successfully"

    except Exception as e:
        logger.error(f"[DEPLOY ERROR] {e}")
        return f"[ERROR] Deploy script failed: {e}"


@tool
def stop_frontend():
    """
    Stop the previously started frontend process if running.
    """
    logger.info("[STOP FRONTEND] Stopping frontend process")
    pid = running_processes.get("frontend")
    if not pid:
        ssh_command = f"{SSH_FRONTEND} 'kill -9 $(lsof -t -i :{FRONTEND_PORT})' && echo 'Frontend stopped'"
        result = subprocess.run(ssh_command, shell=True)
        running_processes["frontend"] = None
        output = result.stdout
        logger.info(f"[FRONTEND STOPPED] {output}")
        return "[INFO] Frontend stopped"
    try:
        ssh_command = f"{SSH_FRONTEND} 'kill -9 {pid}' && echo 'Frontend stopped'"
        result = subprocess.run(ssh_command, shell=True)
        output = result.stdout
        running_processes["frontend"] = None
        logger.info(f"[FRONTEND STOPPED] {output}")
        return f"[FRONTEND STOPPED] PID {pid} killed"
    except Exception as e:
        logger.error(f"[STOP ERROR] {e}")
        running_processes["frontend"] = None
        return f"[ERROR] Failed to stop frontend: {e}"