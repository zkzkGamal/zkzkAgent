from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3-vl:4b-instruct-q4_K_M",
    temperature=0.5,
    timeout=30,
    base_url="http://localhost:11434",
    num_thread=6,
    num_gpu=1,
    top_k=20,
    use_mmap=True,
    keep_alive=1000000
)
