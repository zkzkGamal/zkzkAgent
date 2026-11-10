"""Run ONE benchmark task once and print the result as one JSON line.

    MODEL_TYPE=OLLAMA python3 -m benchmark.run_one --backend local --task T3 --rep 1 --sandbox ~/zkzk-bench/local/T3/rep1
    MODEL_TYPE=OLLAMA python3 -m benchmark.run_one --backend local --warmup

The agent streams its replies to stdout, so while it runs they are sent to
stderr together with the logs. stdout carries only the JSON result, which
run_all.py reads from the last line.
"""

import argparse
import contextlib
import json
import logging
import pathlib
import sys
import time

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage

from benchmark import guards
from benchmark.tasks import get_task
from chat_cli.session import ChatSession
from preprocessing.strip_think_tags import strip_think_tags

# First basicConfig wins, so this format also applies to the agent's own loggers
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

PLAN_APPROVAL = "ok"
CONFIRMATION_ANSWER = "no"  # the benchmark never lets a dangerous tool run
WARMUP_MESSAGE = "this is a warm up message, generate a short response"
MAX_TOOL_INPUT = 300  # characters of each tool input kept in the result
MAX_ANSWER = 1000  # characters of the final answer kept in the result


class Meter(BaseCallbackHandler):
    """Counts model calls, tokens and tool calls across every node of the graph."""

    def __init__(self):
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.tool_calls = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.llm_calls += 1

    def on_llm_end(self, response, **kwargs):
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None) or {}
                self.tokens_in += usage.get("input_tokens", 0)
                self.tokens_out += usage.get("output_tokens", 0)

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "?")
        self.tool_calls.append({"name": name, "input": str(input_str)[:MAX_TOOL_INPUT]})

    def as_row(self) -> dict:
        return {
            "n_llm_calls": self.llm_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "n_tool_calls": len(self.tool_calls),
            "tool_calls": self.tool_calls,
        }


# --------------------------------------------------------------------------- #
# Driving the agent
# --------------------------------------------------------------------------- #
def send(app, state: dict, text: str, meter: Meter) -> dict:
    state["messages"].append(HumanMessage(content=text))
    state["iteration_count"] = 0  # reset step counter for the new request
    return app.invoke(state, config={"callbacks": [meter]})


def run_conversation(app, task, prompt: str, meter: Meter):
    """Send the prompt, then answer like a careful user would: approve the
    plan once, say no to the first dangerous tool, and send the task's
    follow-up once if the agent stopped to ask in plain text."""
    state = send(app, ChatSession.fresh_state(), prompt, meter)
    route = state.get("category")
    approvals, follow_ups, denied_tools = 0, 0, []

    while True:
        pending_tool = (state.get("pending_confirmation") or {}).get("tool_name")
        if pending_tool and not denied_tools:
            logger.info(f"[BENCH] Refusing dangerous tool: {pending_tool}")
            denied_tools.append(pending_tool)
            state = send(app, state, CONFIRMATION_ANSWER, meter)
        elif state.get("pending_plan") and approvals == 0:
            logger.info("[BENCH] Approving plan")
            approvals += 1
            state = send(app, state, PLAN_APPROVAL, meter)
        elif task.follow_up and follow_ups == 0 and not denied_tools:
            logger.info(f"[BENCH] Sending follow-up: {task.follow_up}")
            follow_ups += 1
            state = send(app, state, task.follow_up, meter)
        else:
            return state, route, approvals, follow_ups, denied_tools


def final_answer(state: dict) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage) and message.content:
            return strip_think_tags(str(message.content))
    return ""


def guard_record() -> dict:
    return {
        "blocked_commands": [c[:MAX_TOOL_INPUT] for c in guards.BLOCKED_COMMANDS],
        "skipped_tools": list(guards.SKIPPED_TOOLS),
    }


def emit(row: dict) -> None:
    print(json.dumps(row, default=str), flush=True)


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def warm_up(app, row: dict) -> int:
    state = ChatSession.fresh_state()
    state["messages"] = [HumanMessage(content=WARMUP_MESSAGE)]
    start = time.perf_counter()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            app.invoke(state)
    except Exception as exc:  # noqa: BLE001 — report it; run_all decides what to do
        row["error"] = f"{type(exc).__name__}: {exc}"
        emit(row)
        return 1
    row.update(success=True, wall_s=round(time.perf_counter() - start, 2))
    emit(row)
    return 0


def run_task(app, args, row: dict) -> int:
    task = get_task(args.task)
    sandbox = args.sandbox
    facts = task.setup(sandbox)
    meter = Meter()
    row.update(
        task=task.id,
        task_name=task.name,
        expected_route=task.expected_route,
        sandbox=str(sandbox),
    )

    logger.info(f"[BENCH] {row['backend']} {task.id} ({task.name}) rep {args.rep}")
    start = time.perf_counter()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            state, route, approvals, follow_ups, denied_tools = run_conversation(
                app, task, task.render_prompt(sandbox), meter
            )
    except Exception as exc:  # noqa: BLE001 — a crashing agent is a failed run
        logger.exception("[BENCH] Agent raised an error")
        row.update(
            error=f"{type(exc).__name__}: {exc}",
            wall_s=round(time.perf_counter() - start, 2),
            **guard_record(),  # a crashed run can still show what it tried
            **meter.as_row(),
        )
        emit(row)
        return 1
    wall_s = round(time.perf_counter() - start, 2)

    answer = final_answer(state)
    run = {
        "answer": answer,
        "route": route,
        "tool_calls": meter.tool_calls,
        "denied_tools": denied_tools,
        "blocked_commands": list(guards.BLOCKED_COMMANDS),
        "sandbox": sandbox,
    }
    checks = task.check(run, facts)

    row.update(
        success=all(checks.values()),
        checks=checks,
        route=route,
        route_match=route == task.expected_route,
        approvals=approvals,
        follow_ups=follow_ups,
        denied_tools=denied_tools,
        wall_s=wall_s,
        **guard_record(),
        answer=answer[:MAX_ANSWER],
        **meter.as_row(),
    )
    logger.info(f"[BENCH] {'PASS' if row['success'] else 'FAIL'} {checks}")
    emit(row)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark.run_one", description="Run one zkzkAgent benchmark task once."
    )
    parser.add_argument("--backend", required=True, help="label for the results, e.g. local or nosana")
    parser.add_argument("--task", help="task id, e.g. T3")
    parser.add_argument("--rep", type=int, default=1, help="repeat number (default: 1)")
    parser.add_argument("--sandbox", type=pathlib.Path, help="folder this run may use")
    parser.add_argument(
        "--warmup", action="store_true",
        help="send one untimed message so the model is loaded, then exit",
    )
    args = parser.parse_args()
    if not args.warmup and not (args.task and args.sandbox):
        parser.error("--task and --sandbox are required unless --warmup is given")
    if args.sandbox:
        args.sandbox = args.sandbox.expanduser().resolve()
        args.sandbox.mkdir(parents=True, exist_ok=True)

    row = {
        "backend": args.backend,
        "task": "warmup" if args.warmup else args.task,
        "rep": args.rep,
        "success": False,
        "error": None,
    }
    try:
        guards.install(args.sandbox)
    except (NotImplementedError, RuntimeError) as exc:
        row["error"] = f"guards: {exc}"
        emit(row)
        return 2

    # Heavy import (~5s), only once the guards are in place — same as chat_cli
    from core.agent import app
    from models import LLM as llm_config

    row.update(
        model=llm_config.MODEL_NAME,
        model_type=llm_config.MODEL_TYPE,
        reasoning=getattr(llm_config, "REASONING", None),  # Ollama only
    )
    if args.warmup:
        return warm_up(app, row)
    return run_task(app, args, row)


if __name__ == "__main__":
    sys.exit(main())
