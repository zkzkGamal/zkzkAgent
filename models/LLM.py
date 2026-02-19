from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3:4b-instruct-2507-q4_K_M",
    temperature=0.5,
    timeout=30,
    base_url="http://127.0.0.1:11434",
    num_thread=0,
    num_gpu=1,
    top_k=20,
    use_mmap=True,
    keep_alive=1000000,
    stream=True,
)
