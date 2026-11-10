"""Run every benchmark task N times on ONE backend, one subprocess per run.

    MODEL_TYPE=OLLAMA python3 -m benchmark.run_all --backend local-4b --model qwen3:4b --reps 3
    MODEL_TYPE=NOSANA python3 -m benchmark.run_all --backend nosana --reps 3

--model sets OLLAMA_MODEL / NOSANA_MODEL for the runs (default: from .env);
give each model its own --backend label so its rows get their own file.

Writes to benchmark/results/<date>/ (or --out):
    runs_<backend>.jsonl              one JSON row per run (see run_one.py)
    meta.json                         machine, versions and model, per backend
    logs/<backend>_<task>_rep<n>.log  everything the agent printed and logged

A run that hangs or crashes costs one row, not the whole benchmark.
"""

import argparse
import datetime
import importlib.metadata
import json
import logging
import os
import pathlib
import platform
import shutil
import subprocess
import sys

from benchmark.tasks import TASKS, get_task

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
base_dir = pathlib.Path(__file__).resolve().parent.parent

RUN_TIMEOUT = 900  # seconds per run; Nosana T4 took ~300 s in the dry run
PACKAGES = ["langchain-core", "langgraph", "langchain-openai", "langchain-ollama"]


# --------------------------------------------------------------------------- #
# One run
# --------------------------------------------------------------------------- #
def run_one(run_args: list, log_path: pathlib.Path, timeout: int) -> dict:
    """Start benchmark.run_one in a fresh process and return its JSON row."""
    command = [sys.executable, "-m", "benchmark.run_one", *run_args]
    with open(log_path, "w") as log_file:
        try:
            result = subprocess.run(
                command,
                cwd=base_dir,
                stdout=subprocess.PIPE,
                stderr=log_file,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "timed_out": True, "error": f"timed out after {timeout}s"}

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {
            "success": False,
            "error": f"no result from run_one (exit code {result.returncode}), see {log_path.name}",
        }


def fresh_sandbox(root: pathlib.Path, backend: str, task_id: str, rep: int) -> pathlib.Path:
    sandbox = (root / backend / task_id / f"rep{rep}").resolve()
    sandbox.relative_to(root)  # raises if the path ever escapes the sandbox root
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True)
    return sandbox


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #
def _read_first(path: str, prefix: str) -> str:
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(prefix):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


def _ram_gb() -> str:
    mem_total = _read_first("/proc/meminfo", "MemTotal")  # e.g. "32634292 kB"
    try:
        return f"{int(mem_total.split()[0]) / 1024 ** 2:.0f} GB"
    except (ValueError, IndexError):
        return mem_total


def _command_output(command: list) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, cwd=base_dir)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def machine_info() -> dict:
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "cpu": _read_first("/proc/cpuinfo", "model name"),
        "ram": _ram_gb(),
        "gpu": _command_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
        ),
        "os": platform.platform(),
        "python": platform.python_version(),
        "packages": versions,
        "git_commit": _command_output(["git", "rev-parse", "HEAD"]),
        "git_dirty": bool(_command_output(["git", "status", "--porcelain"])),
    }


def write_meta(out_dir: pathlib.Path, backend: str, info: dict) -> None:
    """meta.json holds one entry per backend, so both runs share one file."""
    meta_path = out_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta[backend] = info
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark.run_all",
        description="Run every zkzkAgent benchmark task N times on one backend.",
    )
    parser.add_argument("--backend", required=True, help="label for the results, e.g. local or nosana")
    parser.add_argument(
        "--model",
        help="model for this backend; sets OLLAMA_MODEL or NOSANA_MODEL (default: from .env)",
    )
    parser.add_argument("--reps", type=int, default=3, help="repeats per task (default: 3)")
    parser.add_argument("--tasks", help="comma-separated task ids (default: all), e.g. T1,T3")
    parser.add_argument(
        "--out", type=pathlib.Path,
        help="results folder (default: benchmark/results/<today>)",
    )
    parser.add_argument(
        "--sandbox-root", type=pathlib.Path, default=pathlib.Path("~/zkzk-bench"),
        help="where per-run sandbox folders go (default: ~/zkzk-bench)",
    )
    parser.add_argument(
        "--timeout", type=int, default=RUN_TIMEOUT,
        help=f"seconds before a run is killed (default: {RUN_TIMEOUT})",
    )
    args = parser.parse_args()

    if not os.environ.get("MODEL_TYPE"):
        parser.error("set MODEL_TYPE explicitly (OLLAMA or NOSANA) so .env can't pick the backend for you")
    model_type = os.environ["MODEL_TYPE"].strip().upper()
    if args.model:
        # Inherited by every run_one subprocess; load_dotenv never overrides it
        os.environ["NOSANA_MODEL" if model_type == "NOSANA" else "OLLAMA_MODEL"] = args.model

    tasks = [get_task(t) for t in args.tasks.split(",")] if args.tasks else TASKS
    out_dir = (args.out or base_dir / "benchmark" / "results" / datetime.date.today().isoformat()).resolve()
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    sandbox_root = args.sandbox_root.expanduser().resolve()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    backend = args.backend

    logger.info(
        f"[BENCH] Warming up {backend} (MODEL_TYPE={model_type}, model={args.model or 'from .env'})"
    )
    warm = run_one(["--backend", backend, "--warmup"], logs_dir / f"{backend}_warmup.log", args.timeout)
    if not warm.get("success"):
        logger.error(f"[BENCH] Warm-up failed, nothing was run: {warm.get('error')}")
        return 1
    if args.model and warm.get("model") != args.model:
        logger.error(f"[BENCH] Asked for {args.model} but the agent loaded {warm.get('model')}")
        return 1
    logger.info(f"[BENCH] {warm.get('model')} ready in {warm.get('wall_s')}s")

    info = machine_info()
    info.update(
        model=warm.get("model"),
        model_type=warm.get("model_type"),
        reasoning=warm.get("reasoning"),
        reps=args.reps,
        tasks=[task.id for task in tasks],
        run_timeout_s=args.timeout,
        started_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )
    if model_type == "OLLAMA":
        # Shows whether the model fit in VRAM ("100% GPU") or spilled onto the CPU
        info["ollama_ps"] = _command_output(["ollama", "ps"])
    write_meta(out_dir, backend, info)

    runs_path = out_dir / f"runs_{backend}.jsonl"
    passes = {task.id: 0 for task in tasks}
    total = args.reps * len(tasks)
    done = 0
    with open(runs_path, "w") as runs_file:
        for rep in range(1, args.reps + 1):
            for task in tasks:
                done += 1
                sandbox = fresh_sandbox(sandbox_root, backend, task.id, rep)
                log_path = logs_dir / f"{backend}_{task.id}_rep{rep}.log"
                row = run_one(
                    ["--backend", backend, "--task", task.id, "--rep", str(rep), "--sandbox", str(sandbox)],
                    log_path,
                    args.timeout,
                )
                # Fill in who/what for rows from runs that died before printing them
                row.setdefault("backend", backend)
                row.setdefault("task", task.id)
                row.setdefault("rep", rep)
                row["log"] = str(log_path.relative_to(out_dir))
                runs_file.write(json.dumps(row) + "\n")
                runs_file.flush()

                passes[task.id] += bool(row.get("success"))
                status = "PASS" if row.get("success") else "FAIL"
                detail = row.get("error") or f"{row.get('n_tool_calls', 0)} tool calls"
                logger.info(
                    f"[BENCH] {done}/{total} {backend} {task.id} rep {rep}: "
                    f"{status} in {row.get('wall_s', '?')}s ({detail})"
                )

    info["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    write_meta(out_dir, backend, info)
    logger.info(
        f"[BENCH] Done: "
        + ", ".join(f"{task_id} {n}/{args.reps}" for task_id, n in passes.items())
        + f" — rows in {runs_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
