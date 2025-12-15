from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3-vl:4b-instruct-q4_K_M",
    temperature=0.5,
    timeout=30,
    model_kwargs={
        "base_url": "http://localhost:11434",
        "num_thread": 4,  # Reduce CPU core usage
        "num_gpu": 1,  # If you have GPU, keep this low
        "top_k": 10,  # small = faster
    },
)
