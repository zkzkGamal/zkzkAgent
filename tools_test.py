from langchain_ollama import ChatOllama
from langchain_core.tools import tool

# 1. Define a dummy tool
@tool
def check_server_health(server_ip: str):
    """Checks the health of a server given its IP address."""
    return "Server is Healthy (200 OK)"

# 2. Initialize the model (using ChatOllama, NOT standard Ollama)
# Note: Ensure the model name matches what you have in `ollama list`
model_name = "qwen3-vl:4b-instruct-q4_K_M"

llm = ChatOllama(
    model=model_name, # Replace with your actual model name
    temperature=0
)

# 3. Bind the tool to the LLM
llm_with_tools = llm.bind_tools([check_server_health])

# 4. Test it
response = llm_with_tools.invoke("Check the health of server 192.168.1.1")

# 5. Check if it decided to call the tool
print(response.tool_calls)