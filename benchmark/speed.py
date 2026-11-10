"""Measure time to first token and generation speed for ONE backend.

    MODEL_TYPE=OLLAMA python3 -m benchmark.speed --backend local-2b --model qwen3.5:2b-q4_K_M --out benchmark/results/<date>
    MODEL_TYPE=NOSANA python3 -m benchmark.speed --backend nosana --model qwen/qwen3.8-27b --out benchmark/results/<date>

Each call is the executor node's real first call: the same system prompt and
all the agent's tool schemas, plus one short question. It goes straight to the
model API with streaming, so every token is seen, including reasoning that
LangChain's OpenAI client hides. Settings (model, reasoning, num_ctx, key)
come from models/LLM.py, like the agent. One untimed warm-up call, then
--reps timed calls. Writes speed_<backend>.jsonl to --out.
"""

import argparse
import datetime
import json
import logging
import os
import pathlib
import sys
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
base_dir = pathlib.Path(__file__).resolve().parent.parent

TIMEOUT = 300  # seconds per call
# A different file mode per call, so no call is an exact repeat of a cached prompt
MODES = ["755", "644", "700", "600", "777", "750", "640", "711", "444", "775"]
QUESTION = (
    "Explain what `chmod {mode}` does to a file in about 120 words. "
    "Answer directly, do not call any tools."
)
NS = 1e9  # Ollama reports durations in nanoseconds


# --------------------------------------------------------------------------- #
# The request
# --------------------------------------------------------------------------- #
def agent_request(mode: str) -> tuple:
    """Messages and tools exactly as the executor node sends them."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from core.loadPrompts import LoadPrompts
    from core.tools import __all__ as tool_functions

    system = LoadPrompts().load_prompt("executor.yaml")[0].content
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": QUESTION.format(mode=mode)},
    ]
    return messages, [convert_to_openai_tool(tool) for tool in tool_functions]


# --------------------------------------------------------------------------- #
# Streaming one call
# --------------------------------------------------------------------------- #
def stream_ollama(cfg, messages: list, tools: list) -> dict:
    body = {
        "model": cfg.MODEL_NAME,
        "messages": messages,
        "tools": tools,
        "stream": True,
        "keep_alive": -1,
        "think": cfg.REASONING,
    }
    if cfg.NUM_CTX:
        body["options"] = {"num_ctx": cfg.NUM_CTX}

    start = time.perf_counter()
    first, final, seen = None, {}, {"reasoning": False, "tool_call": False}
    with httpx.stream("POST", f"{cfg.BASE_URL}/api/chat", json=body, timeout=TIMEOUT) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            message = chunk.get("message") or {}
            seen["reasoning"] |= bool(message.get("thinking"))
            seen["tool_call"] |= bool(message.get("tool_calls"))
            if first is None and (message.get("content") or message.get("thinking") or message.get("tool_calls")):
                first = time.perf_counter()
            if chunk.get("done"):
                final = chunk
    end = time.perf_counter()

    decode_s = final.get("eval_duration", 0) / NS
    return {
        **_timing(start, first, end, final.get("prompt_eval_count"), final.get("eval_count")),
        "reasoning_seen": seen["reasoning"],
        "tool_called": seen["tool_call"],
        # Ollama's own clock: no HTTP or Python overhead
        "server_prompt_s": round(final.get("prompt_eval_duration", 0) / NS, 3),
        "server_decode_s": round(decode_s, 3),
        "server_tok_per_s": round(final["eval_count"] / decode_s, 1) if decode_s and final.get("eval_count") else None,
    }


def stream_openai(cfg, messages: list, tools: list) -> dict:
    """Nosana's OpenAI-compatible API (any /v1/chat/completions server)."""
    body = {
        "model": cfg.MODEL_NAME,
        "messages": messages,
        "tools": tools,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    headers = {"Authorization": f"Bearer {cfg.API_KEY}"}

    start = time.perf_counter()
    first, usage, seen = None, {}, {"reasoning": False, "tool_call": False}
    with httpx.stream(
        "POST", f"{cfg.BASE_URL}/chat/completions", json=body, headers=headers, timeout=TIMEOUT
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                seen["reasoning"] |= bool(reasoning)
                seen["tool_call"] |= bool(delta.get("tool_calls"))
                if first is None and (delta.get("content") or reasoning or delta.get("tool_calls")):
                    first = time.perf_counter()
    end = time.perf_counter()

    return {
        **_timing(start, first, end, usage.get("prompt_tokens"), usage.get("completion_tokens")),
        "reasoning_seen": seen["reasoning"],
        "tool_called": seen["tool_call"],
    }


def _timing(start: float, first, end: float, tokens_in, tokens_out) -> dict:
    """ttft_s: until the first token of any kind (reasoning included), as the
    agent receives it. tok_per_s: output tokens over the time after that."""
    ttft = first - start if first is not None else None
    generating = end - first if first is not None else None
    return {
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "total_s": round(end - start, 3),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tok_per_s": round(tokens_out / generating, 1) if tokens_out and generating else None,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark.speed", description="Measure time to first token and tokens per second."
    )
    parser.add_argument("--backend", required=True, help="label for the results, e.g. local-2b or nosana")
    parser.add_argument(
        "--model", help="model for this backend; sets OLLAMA_MODEL or NOSANA_MODEL (default: from .env)"
    )
    parser.add_argument(
        "--reps", type=int, default=5, help=f"timed calls (default: 5, max: {len(MODES) - 1})"
    )
    parser.add_argument(
        "--out", type=pathlib.Path, help="results folder (default: benchmark/results/<today>)"
    )
    args = parser.parse_args()

    if not os.environ.get("MODEL_TYPE"):
        parser.error("set MODEL_TYPE explicitly (OLLAMA or NOSANA) so .env can't pick the backend for you")
    if not 1 <= args.reps < len(MODES):
        parser.error(f"--reps must be between 1 and {len(MODES) - 1}")
    model_type = os.environ["MODEL_TYPE"].strip().upper()
    if args.model:
        os.environ["NOSANA_MODEL" if model_type == "NOSANA" else "OLLAMA_MODEL"] = args.model

    from models import LLM as cfg

    stream = stream_ollama if cfg.MODEL_TYPE == "OLLAMA" else stream_openai
    out_dir = (args.out or base_dir / "benchmark" / "results" / datetime.date.today().isoformat()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    base_row = {
        "backend": args.backend,
        "model": cfg.MODEL_NAME,
        "model_type": cfg.MODEL_TYPE,
        "reasoning": getattr(cfg, "REASONING", None),
        "num_ctx": getattr(cfg, "NUM_CTX", None),
    }

    logger.info(f"[BENCH] Warming up {args.backend} ({cfg.MODEL_NAME})")
    try:
        stream(cfg, *agent_request(MODES[-1]))
    except httpx.HTTPError as exc:
        logger.error(f"[BENCH] Warm-up failed, nothing was measured: {type(exc).__name__}: {exc}")
        return 1

    speed_path = out_dir / f"speed_{args.backend}.jsonl"
    with open(speed_path, "w") as speed_file:
        for rep in range(1, args.reps + 1):
            mode = MODES[rep - 1]
            row = {**base_row, "rep": rep, "question": f"chmod {mode}", "error": None}
            try:
                row.update(stream(cfg, *agent_request(mode)))
            except httpx.HTTPError as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            speed_file.write(json.dumps(row) + "\n")
            speed_file.flush()
            logger.info(
                f"[BENCH] {rep}/{args.reps} {args.backend}: first token {row.get('ttft_s')}s, "
                f"{row.get('tok_per_s')} tok/s, {row.get('tokens_in')} in / {row.get('tokens_out')} out"
                + (f" ({row['error']})" if row["error"] else "")
            )

    logger.info(f"[BENCH] Done — rows in {speed_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
