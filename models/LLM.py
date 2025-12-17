from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3-vl:4b-instruct-q4_K_M",
    temperature=0.5,
    timeout=30,
    model_kwargs={
        "base_url": "http://localhost:11434",
        "num_thread": 6,  # max threads for CPU
        "num_gpu": 1,     # keep GPU usage
        "top_k": 20,      # slightly higher for quality
        "num_ctx": 1024,  
        "use_mmap": True, # reduces RAM load
    },
)
