from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3-vl:4b-instruct-q4_K_M",
    temperature=0,
    base_url="http://127.0.0.1:11434",  # force local Ollama
    timeout=120,
)
