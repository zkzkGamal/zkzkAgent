from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3:4b-instruct-2507-q4_K_M",
    timeout=30,
    base_url="http://127.0.0.1:11434",
    use_mmap=True,
    keep_alive=1000000,
    stream=True,
)
