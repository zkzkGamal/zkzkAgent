"""Trace what zkzkAgent does when Nosana drops out in the middle of a task.

    python3 -m benchmark.dropout --list
    python3 -m benchmark.dropout --all --out benchmark/results/<date>-dropout
    python3 -m benchmark.dropout --all --only hybrid-continue --out ...   # cases whose id contains it
    python3 -m benchmark.dropout --report benchmark/results/<date>-dropout

Each case runs a benchmark task (T1, T4 build_app or T5 safety_install) and
cuts Nosana off at its k-th model call. The cut happens in the HTTP transport
under the OpenAI client, so the client's own retries and timeouts behave
exactly as they do in the agent. Failure types:

    refused    the connection is refused (network down)
    503        Nosana answers 503 (no GPU is serving the model)
    timeout    every request times out (raised at once; the row gives the real wait)
    401        Nosana answers 401 (bad key, or no credits left)
    midstream  the reply starts streaming, then the connection drops; refused after that

Modes (the M2 agent, see models/selector.py):

    nosana     every node on Nosana, no fallback
    hybrid     MODEL_TYPE=HYBRID: routing and chat on the local 2B (8K window),
               planning and tools on Nosana, with the local fallback on

When a model failure stops the task, the harness replies like a user would:
"continue" (finish on the local model from a handover summary; Nosana stays
down, an outage) or "retry" (Nosana comes back first, a blip). Local-down
cases point the local model at a closed port while Nosana works.

The 15 Nov modes (shipped, fb2b, fb4b) measured the code at ec7a1e6; check
out that commit to rerun them. The harness swaps the selector the nodes use;
the agent's code is not changed. One subprocess per case. Writes
dropout.jsonl (one row per case, with a timeline of every model and tool
call), logs/<case>.log and summary.md to --out.

--primary-url/--primary-model point the "Nosana" side at another
OpenAI-compatible server (e.g. Ollama's /v1) to test the harness for free.
"""

import argparse
import contextlib
import dataclasses
import datetime
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import httpx
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
base_dir = pathlib.Path(__file__).resolve().parent.parent

NOSANA_MODEL = "qwen/qwen3.8-27b"
PRICE = (0.20, 2.00)  # USD per 1M input / output tokens on Nosana
OLLAMA_URL = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
CLOSED_PORT_URL = "http://127.0.0.1:9"  # nothing listens here: the local model is "down"
# The local side of MODEL_TYPE=HYBRID, as models/LLM.py builds it
LOCAL_MODEL = {"model": "qwen3.5:2b-q4_K_M", "reasoning": False, "num_ctx": 8192}
MODES = ["nosana", "hybrid"]
OLD_MODES = ["shipped", "fb2b", "fb4b"]
MAX_RECOVERIES = 2  # retry/continue replies per case
CASE_TIMEOUT = 1200  # seconds per case: Nosana's plan call alone can stream for ~6 min
PREVIEW = 160  # characters kept from replies, tool inputs and outputs


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class Case:
    task: str
    cut_at: int  # Nosana fails from its k-th model call on (0: never)
    kind: str
    mode: str
    reply: str = "continue"  # what the user answers when a failure stops the task
    local_down: bool = False  # the local model can't be reached; Nosana works

    @property
    def id(self) -> str:
        if self.local_down:
            return f"{self.task}-localdown-{self.mode}"
        return f"{self.task}-cut{self.cut_at}-{self.kind}-{self.mode}-{self.reply}"


def build_cases() -> list:
    """In hybrid mode, routing is local, so Nosana's call 1 is the plan (T4) or
    the first tool step (T5): hybrid cut3 is the same point as the 15 Nov cut4."""
    return [
        *(Case("T4", k, "refused", "hybrid") for k in range(1, 8)),  # outage: finish locally
        *(Case("T5", k, "refused", "hybrid") for k in range(1, 4)),
        *(Case("T4", 3, kind, "hybrid", reply="retry") for kind in ("refused", "503", "timeout", "midstream")),
        Case("T4", 3, "401", "hybrid"),  # a bad key: retrying can't help
        Case("T4", 3, "refused", "nosana", reply="retry"),  # no fallback: stop, keep progress, retry
        Case("T1", 0, "none", "hybrid", local_down=True),
        Case("T4", 0, "none", "hybrid", local_down=True),
    ]


CASES = build_cases()
CASES_BY_ID = {case.id: case for case in CASES}


# --------------------------------------------------------------------------- #
# The fault: an HTTP transport that can be cut
# --------------------------------------------------------------------------- #
_VISIBLE = re.compile(rb'"content":\s*"[^"]|"tool_calls":\s*\[')


class _DroppingStream(httpx.SyncByteStream):
    """Lets a streamed reply through until visible output starts, then drops it."""

    KEEP_CHUNKS = 20  # chunks let through after the first visible text or tool call

    def __init__(self, inner, request, on_drop):
        self._inner, self._request, self._on_drop = inner, request, on_drop

    def __iter__(self):
        started, after = False, 0
        for chunk in self._inner:
            yield chunk
            if not started:
                started = bool(_VISIBLE.search(chunk))
            else:
                after += 1
                if after >= self.KEEP_CHUNKS:
                    self._on_drop()
                    raise httpx.ReadError("simulated: connection dropped mid-reply", request=self._request)

    def close(self):
        self._inner.close()


class FaultTransport(httpx.BaseTransport):
    """Forwards requests to the real server until cut(), then fails them."""

    def __init__(self):
        self._real = httpx.HTTPTransport()
        self.kind = None  # None: the server works
        self.forwarded = 0
        self.failed = []  # every request after the cut and what it got
        self._midstream_used = False
        self._t0 = time.perf_counter()

    def cut(self, kind: str) -> None:
        self.kind = kind

    def restore(self) -> None:
        self.kind = None

    def _fail(self, got: str) -> None:
        self.failed.append({"at_s": round(time.perf_counter() - self._t0, 2), "got": got})

    def handle_request(self, request):
        if self.kind is None:
            self.forwarded += 1
            return self._real.handle_request(request)
        if self.kind == "midstream" and not self._midstream_used:
            self._midstream_used = True
            self.forwarded += 1
            response = self._real.handle_request(request)
            stream = _DroppingStream(response.stream, request, lambda: self._fail("dropped mid-reply"))
            return httpx.Response(
                response.status_code, headers=response.headers, stream=stream,
                extensions=response.extensions, request=request,
            )
        if self.kind in ("503", "401"):
            self._fail(self.kind)
            message = "no GPU is serving this model" if self.kind == "503" else "invalid API key or no credits left"
            return httpx.Response(int(self.kind), json={"error": {"message": f"simulated: {message}"}}, request=request)
        if self.kind == "timeout":
            self._fail("timeout")
            raise httpx.ReadTimeout("simulated: no reply before the timeout", request=request)
        self._fail("refused")
        raise httpx.ConnectError("simulated: connection refused", request=request)

    def close(self):
        self._real.close()


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def nosana_model(transport: FaultTransport, args):
    """The agent's Nosana model (same settings as models/LLM.py), over the fault transport."""
    from langchain_openai import ChatOpenAI

    from models import LLM as cfg

    return ChatOpenAI(
        model=args.primary_model or cfg.MODEL_NAME,
        base_url=args.primary_url or cfg.BASE_URL,
        api_key="local-test" if args.primary_url else cfg.API_KEY,
        timeout=httpx.Timeout(cfg.CONFIG.nosana_timeout, connect=5.0),
        max_retries=cfg.CONFIG.nosana_max_retries,
        stream_usage=True,
        http_client=httpx.Client(transport=transport),
    )


def local_model(down: bool = False):
    from langchain_ollama import ChatOllama

    from models import LLM as cfg

    return ChatOllama(
        model=LOCAL_MODEL["model"], base_url=CLOSED_PORT_URL if down else OLLAMA_URL, keep_alive=-1,
        reasoning=LOCAL_MODEL["reasoning"], num_ctx=LOCAL_MODEL["num_ctx"],
        client_kwargs={"timeout": cfg.CONFIG.ollama_timeout},
    )


def install_selector(case: Case, transport: FaultTransport, args) -> None:
    """Give the nodes the case's models: Nosana over the fault transport, plus the local 2B in hybrid."""
    from models import LLM as cfg
    from models import selector

    models = {"nosana": nosana_model(transport, args)}
    names = {"nosana": args.primary_model or cfg.MODEL_NAME}
    if case.mode == "hybrid":
        models["local"], names["local"] = local_model(case.local_down), LOCAL_MODEL["model"]
        roles, fallback = dict(cfg.HYBRID_ROLES), True
    else:
        roles, fallback = dict.fromkeys(cfg.ROLES, "nosana"), False
    selector.install(selector.ModelSelector(models, names, roles, fallback, cfg.CONFIG.cooldown_s))


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #
def _preview(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:PREVIEW]


def _request_chars(messages, tools) -> int:
    """Characters sent in one model call: messages, tool calls in them, tool schemas."""
    total = 0
    for batch in messages:
        for message in batch:
            content = message.content
            total += len(content if isinstance(content, str) else json.dumps(content, default=str))
            if getattr(message, "tool_calls", None):
                total += len(json.dumps(message.tool_calls, default=str))
    return total + (len(json.dumps(tools, default=str)) if tools else 0)


class Tracer(BaseCallbackHandler):
    """Records every model and tool call in order, and cuts Nosana at call k."""

    def __init__(self, transport: FaultTransport, case: Case):
        self.transport, self.case = transport, case
        self.nosana_calls = 0
        self.cut_node = None
        self.timeline = []
        self._open = {}  # run_id -> (event, start time)
        self._t0 = time.perf_counter()

    def _start(self, run_id, event: dict) -> None:
        event["start_s"] = round(time.perf_counter() - self._t0, 2)
        self._open[run_id] = (event, time.perf_counter())
        self.timeline.append(event)

    def _finish(self, run_id, **fields) -> None:
        event, start = self._open.pop(run_id, (None, None))
        if event is not None:
            event.update(secs=round(time.perf_counter() - start, 2), **fields)

    def mark(self, reply: str) -> None:
        """The harness replied retry/continue after a stop: note it in the timeline."""
        self.timeline.append({"type": "user", "text": reply, "start_s": round(time.perf_counter() - self._t0, 2)})

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, **kwargs):
        params = kwargs.get("invocation_params") or {}
        who = "nosana" if "openai" in str(params.get("_type", "")) else "local"
        event = {
            "type": "model", "model": who, "node": (metadata or {}).get("langgraph_node"),
            "request_chars": _request_chars(messages, params.get("tools")), "cut_here": False,
        }
        if who == "nosana":
            self.nosana_calls += 1
            if self.cut_node is None and self.nosana_calls == self.case.cut_at:
                self.transport.cut(self.case.kind)
                self.cut_node = event["node"]
                event["cut_here"] = True
                logger.info(f"[DROPOUT] Cutting Nosana ({self.case.kind}) at call {self.case.cut_at} ({event['node']})")
        self._start(run_id, event)

    def on_llm_end(self, response, *, run_id, **kwargs):
        message = None
        with contextlib.suppress(IndexError, AttributeError):
            message = response.generations[0][0].message
        usage = getattr(message, "usage_metadata", None) or {}
        self._finish(
            run_id, ok=True,
            tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
            tool_calls=[call["name"] for call in getattr(message, "tool_calls", None) or []],
            reply=_preview(getattr(message, "content", "") or ""),
        )

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, ok=False, error=f"{type(error).__name__}: {str(error)[:200]}")

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = kwargs.get("name") or (serialized or {}).get("name", "?")
        self._start(run_id, {"type": "tool", "name": name, "input": str(input_str)[:300]})

    def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish(run_id, ok=True, output=_preview(str(getattr(output, "content", output))))

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, ok=False, error=f"{type(error).__name__}: {str(error)[:200]}")


def _model_events(rows, model: str) -> list:
    return [e for row in rows for e in row.get("timeline") or []
            if e["type"] == "model" and e["model"] == model and e.get("ok") and e.get("tokens_in")]


def estimate_prompts(rows: list) -> float | None:
    """Estimate each local call's full prompt in tokens, to see what the 4K window cut.

    Ollama reports only the tokens it kept (it silently drops older messages,
    or cuts the prompt itself), so the full size comes from characters, at
    tokens per character measured on Nosana's exact counts in the same folder
    (0.27–0.31 in the first run). The local templates count 20–40% fewer
    tokens than this, so values just over the window may still have fit.
    """
    nosana = _model_events(rows, "nosana")
    chars = sum(e["request_chars"] for e in nosana)
    per_char = sum(e["tokens_in"] for e in nosana) / chars if chars else None
    for row in rows:
        local = _model_events([row], "local")
        for event in local:
            if per_char:
                event["est_prompt_tokens"] = round(event["request_chars"] * per_char)
                event["over_window"] = event["est_prompt_tokens"] > (row.get("local_window") or 4096)
        row.setdefault("local", {})["over_window"] = sum(bool(e.get("over_window")) for e in local)
    return per_char


# --------------------------------------------------------------------------- #
# One case (runs in its own process)
# --------------------------------------------------------------------------- #
def say(app, state: dict, text: str, tracer: Tracer, turns: list):
    """One user turn. On an error, keep the state from before the turn, like chat_cli."""
    state["messages"].append(HumanMessage(content=text))
    state["iteration_count"] = 0
    start = time.perf_counter()
    try:
        new_state = app.invoke(state, config={"callbacks": [tracer]})
    except Exception as exc:  # noqa: BLE001 — the error is what we are tracing
        logger.exception("[DROPOUT] The turn raised an error")
        turns.append({"user": text, "ok": False, "secs": round(time.perf_counter() - start, 2),
                      "error": f"{type(exc).__name__}: {exc}"[:300]})
        return state, exc
    turns.append({"user": text, "ok": True, "secs": round(time.perf_counter() - start, 2),
                  "route": new_state.get("category")})
    return new_state, None


def converse(app, task, prompt: str, tracer: Tracer, case: Case):
    """Answer like run_one.py does (approve the plan once, answer each
    confirmation, send the follow-up once). When a model failure stops the
    task, reply with the case's choice: "retry" brings Nosana back first,
    "continue" leaves it down. Stops at a crash."""
    from benchmark.run_one import MAX_CONFIRMATIONS, PLAN_APPROVAL, confirmation_answer
    from chat_cli.session import ChatSession

    state, turns = ChatSession.fresh_state(), []
    talk = {"denied": [], "approved": [], "interruptions": 0, "replies": [], "offers": []}
    approvals = follow_ups = 0
    text = prompt
    while text is not None:
        state, error = say(app, state, text, tracer, turns)
        if error is not None:
            break  # a crash: the M2 agent should stop cleanly instead
        stopped = state.get("interrupted")
        if stopped:
            talk["interruptions"] += 1
            talk["offers"].append(str(state["messages"][-1].content))
        pending = state.get("pending_confirmation") or {}
        if pending.get("tool_name") and len(talk["denied"]) + len(talk["approved"]) < MAX_CONFIRMATIONS:
            call = {"name": pending["tool_name"], "args": pending.get("tool_args") or {}}
            text = confirmation_answer(call["name"], call["args"])
            talk["approved" if text == "yes" else "denied"].append(call)
        elif stopped and len(talk["replies"]) < MAX_RECOVERIES:
            text = case.reply
            if text == "retry":
                tracer.transport.restore()
                logger.info("[DROPOUT] Nosana is back: replying retry")
            talk["replies"].append(text)
            tracer.mark(text)
        elif state.get("pending_plan") and approvals == 0:
            approvals += 1
            text = PLAN_APPROVAL
        elif task.follow_up and follow_ups == 0 and not talk["denied"]:
            follow_ups += 1
            text = task.follow_up
        else:
            text = None
    return state, turns, talk


def recovery_steps(timeline: list) -> tuple:
    """(steps that ran before the first retry/continue, steps redone after it)."""
    first = next((i for i, e in enumerate(timeline) if e["type"] == "user"), None)
    tools = lambda events: [(e["name"], e["input"]) for e in events if e["type"] == "tool" and e.get("ok", True)]
    if first is None:
        return len(tools(timeline)), 0
    before, after = tools(timeline[:first]), tools(timeline[first:])
    return len(before), sum(1 for step in after if step in before)


def list_files(sandbox: pathlib.Path) -> list:
    return sorted(
        f"{path.relative_to(sandbox)} ({path.stat().st_size} B)"
        for path in sandbox.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def run_case(case: Case, sandbox: pathlib.Path, args) -> dict:
    from benchmark import guards
    from benchmark.run_one import final_answer
    from benchmark.tasks import get_task

    guards.install(sandbox)
    from core.agent import app  # heavy import, only once the guards are in place
    from models import LLM as cfg

    transport = FaultTransport()
    install_selector(case, transport, args)

    task = get_task(case.task)
    facts = task.setup(sandbox)
    tracer = Tracer(transport, case)
    logger.info(f"[DROPOUT] {case.id}")
    start = time.perf_counter()
    with contextlib.redirect_stdout(sys.stderr):
        state, turns, talk = converse(app, task, task.render_prompt(sandbox), tracer, case)
    wall_s = round(time.perf_counter() - start, 2)

    tools = [{"name": e["name"], "input": e["input"]} for e in tracer.timeline if e["type"] == "tool"]
    answer = final_answer(state)
    denied = [call["name"] for call in talk["denied"]]
    checks = task.check(
        {"answer": answer, "route": state.get("category"), "tool_calls": tools,
         "denied_tools": denied, "denied_calls": talk["denied"],
         "blocked_commands": list(guards.BLOCKED_COMMANDS), "sandbox": sandbox},
        facts,
    )
    steps_kept, steps_redone = recovery_steps(tracer.timeline)
    models =[e for e in tracer.timeline if e["type"] == "model"]
    nosana_ok = [e for e in models if e["model"] == "nosana" and e.get("ok")]
    local_ok = [e for e in models if e["model"] == "local" and e.get("ok")]
    tokens_in = sum(e.get("tokens_in") or 0 for e in nosana_ok)
    tokens_out = sum(e.get("tokens_out") or 0 for e in nosana_ok)
    timeout_s = cfg.CONFIG.nosana_timeout
    return {
        **dataclasses.asdict(case),
        "id": case.id,
        "success": all(checks.values()) and all(turn["ok"] for turn in turns[-1:]),
        "checks": checks,
        "cut_happened": tracer.cut_node is not None,
        "cut_node": tracer.cut_node,
        "turns": turns,
        "answer": answer[:1000],
        "denied_tools": denied,
        "approved_calls": talk["approved"],
        "interruptions": talk["interruptions"],
        "replies": talk["replies"],
        "continues": talk["replies"].count("continue"),
        "offer": talk["offers"][0] if talk["offers"] else None,
        "steps_kept": steps_kept,
        "steps_redone": steps_redone,
        "blocked_commands": [c[:300] for c in guards.BLOCKED_COMMANDS],
        "skipped_tools": list(guards.SKIPPED_TOOLS),
        "files": list_files(sandbox),
        "wall_s": wall_s,
        "failed_requests": transport.failed,
        "real_wait_s": len(transport.failed) * timeout_s if case.kind == "timeout" else None,
        "nosana": {"calls_ok": len(nosana_ok), "tokens_in": tokens_in, "tokens_out": tokens_out,
                   "cost": round((tokens_in * PRICE[0] + tokens_out * PRICE[1]) / 1e6, 5)},
        "local": {"model": LOCAL_MODEL["model"] if case.mode == "hybrid" else None, "calls_ok": len(local_ok)},
        "local_window": LOCAL_MODEL["num_ctx"] if case.mode == "hybrid" else None,
        "timeline": tracer.timeline,
        "primary": args.primary_model or cfg.MODEL_NAME,
    }


# --------------------------------------------------------------------------- #
# All cases (one subprocess each)
# --------------------------------------------------------------------------- #
def _ollama(command: list) -> str:
    result = subprocess.run(["ollama", *command], capture_output=True, text=True, timeout=60)
    return result.stdout


def load_only(model: str) -> None:
    """Unload every model, then load `model` so the first fallback isn't a cold start."""
    for line in _ollama(["ps"]).splitlines()[1:]:
        if line.split():
            _ollama(["stop", line.split()[0]])
    httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": model, "keep_alive": -1, "options": {"num_ctx": LOCAL_MODEL["num_ctx"]}},
        timeout=300,
    )
    logger.info(f"[DROPOUT] Loaded {model}: {_ollama(['ps']).splitlines()[-1]}")


def run_subprocess(case: Case, sandbox: pathlib.Path, log_path: pathlib.Path, args) -> dict:
    command = [sys.executable, "-m", "benchmark.dropout", "--case", case.id, "--sandbox", str(sandbox)]
    if args.primary_url:
        command += ["--primary-url", args.primary_url, "--primary-model", args.primary_model]
    env = {**os.environ, "MODEL_TYPE": "NOSANA", "PYTHONUNBUFFERED": "1"}
    env.setdefault("NOSANA_MODEL", NOSANA_MODEL)  # skips the live model lookup at import
    with open(log_path, "w") as log_file:
        try:
            result = subprocess.run(
                command, cwd=base_dir, stdout=subprocess.PIPE, stderr=log_file,
                text=True, timeout=args.timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "timed_out": True, "error": f"timed out after {args.timeout}s"}
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"success": False, "error": f"no result (exit code {result.returncode}), see {log_path.name}"}


def run_all(args) -> int:
    from benchmark.run_all import fresh_sandbox

    wanted = [s for s in (args.only or "").split(",") if s]
    cases = [c for c in CASES if not wanted or any(s in c.id for s in wanted)]
    if not cases:
        logger.error(f"[DROPOUT] No case id contains {wanted}; see --list")
        return 1
    out_dir = args.out.resolve()
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    sandbox_root = args.sandbox_root.expanduser().resolve()
    rows_path = out_dir / "dropout.jsonl"

    if any(c.mode == "hybrid" for c in cases):
        load_only(LOCAL_MODEL["model"])  # one local model for every case
    for n, case in enumerate(cases, 1):
        sandbox = fresh_sandbox(sandbox_root, "dropout", case.id, 1)
        log_path = out_dir / "logs" / f"{case.id}.log"
        row = run_subprocess(case, sandbox, log_path, args)
        row.setdefault("id", case.id)
        row.update(log=str(log_path.relative_to(out_dir)), finished_at=datetime.datetime.now().isoformat(timespec="seconds"))
        with open(rows_path, "a") as rows_file:  # appended: a rerun of one case replaces it in the report
            rows_file.write(json.dumps(row, default=str) + "\n")
        logger.info(
            f"[DROPOUT] {n}/{len(cases)} {case.id}: {result_label(row)} in {row.get('wall_s', '?')}s, "
            f"Nosana ${row.get('nosana', {}).get('cost', 0):.4f}"
        )

    write_summary(out_dir)
    return 0


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def hidden_local_error(row: dict):
    """When Nosana and the fallback both fail, with_fallbacks raises Nosana's
    error, so the local model's own error is only in the timeline."""
    models = [e for e in row.get("timeline") or [] if e["type"] == "model"]
    if models and models[-1]["model"] == "local" and not models[-1].get("ok"):
        return models[-1].get("error")
    return None


def result_label(row: dict) -> str:
    if row.get("error") or row.get("timed_out"):
        return f"harness error: {row.get('error')}"
    turns = row.get("turns") or []
    failed = [t for t in turns if not t["ok"]]
    if failed and not turns[-1]["ok"]:
        label = "✖ crashed: " + failed[-1]["error"].split(":")[0]
        local = hidden_local_error(row)
        if local:
            label += f" (really the local model: {local.split(':')[0]})"
    elif row.get("interruptions"):
        label = "stopped → " + " → ".join(row.get("replies") or ["(no reply)"])
    elif row.get("local_down"):
        label = "local model down"
    elif not row.get("cut_happened"):
        label = "no cut (finished first)"
    else:
        label = "kept going"
    return label + (" → ✅ passed" if row.get("success") else " → ❌ checks failed")


def timeline_line(row: dict) -> str:
    """classify:N✓ → ✂ plan:N✗ → plan:L✓ → execute:L✓[write_file] ..."""
    parts = []
    for event in row.get("timeline") or []:
        if event["type"] == "user":
            parts.append(f"⏎ {event['text']}")
            continue
        if event["type"] == "tool":
            if not event.get("ok", True):
                parts.append(f"⚠{event['name']}✗")
            continue
        mark = "✓" if event.get("ok") else "✗"
        if event["model"] == "local" and not event.get("ok"):
            mark += f"({(event.get('error') or '?').split(':')[0]})"
        tools =f"[{','.join(event.get('tool_calls') or [])}]" if event.get("tool_calls") else ""
        size = ""
        if event.get("est_prompt_tokens"):
            size = f"({event['est_prompt_tokens'] / 1000:.1f}K{'!' if event.get('over_window') else ''})"
        cut = "✂ " if event.get("cut_here") else ""
        parts.append(f"{cut}{event['node']}:{'N' if event['model'] == 'nosana' else 'L'}{mark}{tools}{size}")
    return " → ".join(parts)


def write_summary(out_dir: pathlib.Path) -> str:
    rows = {}
    for line in (out_dir / "dropout.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row  # last one wins
    order = [c.id for c in CASES if c.id in rows] + [i for i in rows if i not in CASES_BY_ID]
    per_char = estimate_prompts(list(rows.values()))

    lines = [
        f"# zkzkAgent: Nosana dropping out mid-task — {out_dir.name}", "",
        "Each case cuts Nosana off from its k-th model call. `hybrid` is `MODEL_TYPE=HYBRID`",
        f"(routing and chat on {LOCAL_MODEL['model']} with an {LOCAL_MODEL['num_ctx']:,}-token window, planning and tools",
        "on Nosana); `nosana` has no fallback. When a failure stops the task, the harness replies",
        "`continue` (Nosana stays down) or `retry` (Nosana is back first).",
        "", "## Totals", "",
        "| Group | Cases | Passed | Crashed | Stopped cleanly | Steps redone after recovery |",
        "|---|---|---|---|---|---|",
    ]
    groups = {}
    for case_id in order:
        row = rows[case_id]
        if row.get("local_down"):
            key = f"{row.get('task')} {row.get('mode')}: local model down"
        else:
            key = f"{row.get('task')} {row.get('mode')}: {row.get('kind')} → {row.get('reply')}"
        groups.setdefault(key, []).append(row)
    for key, group in groups.items():
        crashed = sum(1 for r in group if (r.get("turns") or [{}])[-1].get("ok") is False)
        lines.append("| " + " | ".join([
            key, str(len(group)), str(sum(bool(r.get("success")) for r in group)), str(crashed),
            str(sum(1 for r in group if r.get("interruptions"))),
            str(sum(r.get("steps_redone") or 0 for r in group)),
        ]) + " |")

    lines += [
        "", "## Cases", "",
        "| Case | Cut at | Failure | Reply | Result | Checks | Calls (Nosana / local) | Steps kept | Steps redone | Failed Nosana requests | Local calls over window (est.) | Time (s) | Nosana cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for case_id in order:
        row = rows[case_id]
        checks = row.get("checks") or {}
        passed = sum(bool(v) for v in checks.values())
        failed = row.get("failed_requests") or []
        wait = f" (real wait ≈ {row['real_wait_s']:.0f}s)" if row.get("real_wait_s") else ""
        lines.append("| " + " | ".join([
            f"`{case_id}`",
            f"{row.get('cut_at')} ({row.get('cut_node') or '—'})",
            row.get("kind", "—"),
            ", ".join(row.get("replies") or []) or "—",
            result_label(row),
            f"{passed}/{len(checks)}" if checks else "—",
            f"{row.get('nosana', {}).get('calls_ok', 0)} / {row.get('local', {}).get('calls_ok', 0)}",
            str(row.get("steps_kept", "—")),
            str(row.get("steps_redone", "—")),
            f"{len(failed)}{wait}",
            str(row.get("local", {}).get("over_window", 0)),
            f"{row.get('wall_s', 0):.0f}",
            f"${row.get('nosana', {}).get('cost', 0):.4f}",
        ]) + " |")

    lines += [
        "", "## Timelines", "",
        "`N` = Nosana, `L` = local, ✂ = where Nosana was cut, ⏎ = the harness's reply after a stop.",
        f"`(6.2K!)` = the prompt sent to the local model, estimated at {per_char or 0:.3f} tokens per character",
        "(measured on Nosana's exact counts); `!` = over the local window.", "",
    ]
    for case_id in order:
        row = rows[case_id]
        lines += [f"**{case_id}**: {timeline_line(row)}", ""]
        if row.get("offer"):
            lines += [f"- the agent stopped and said: `{row['offer'].splitlines()[0][:200]}`"]
        for turn in row.get("turns") or []:
            if not turn["ok"]:
                lines += [f"- the user typed `{turn['user'][:60]}` and got: `{turn['error'][:200]}`"]
        if row.get("files"):
            lines += [f"- files: {', '.join(row['files'])}"]
        lines += [""]

    total = sum(r.get("nosana", {}).get("cost", 0) for r in rows.values())
    lines += [f"Nosana cost of all cases: ${total:.4f} (tokens × ${PRICE[0]:.2f} / ${PRICE[1]:.2f} per 1M in / out)."]
    summary = "\n".join(lines) + "\n"
    (out_dir / "summary.md").write_text(summary)
    return summary


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(prog="benchmark.dropout", description=__doc__.split("\n")[0])
    parser.add_argument("--list", action="store_true", help="print the case ids and exit")
    parser.add_argument("--all", action="store_true", help="run every case (or --only), one subprocess each")
    parser.add_argument("--only", help="comma-separated parts of case ids, e.g. shipped,T5-cut2")
    parser.add_argument("--case", help="run one case in this process (used by --all)")
    parser.add_argument("--report", type=pathlib.Path, metavar="DIR", help="rewrite DIR/summary.md and exit")
    parser.add_argument("--out", type=pathlib.Path, help="results folder for --all")
    parser.add_argument("--sandbox", type=pathlib.Path, help="folder the one --case may use")
    parser.add_argument("--sandbox-root", type=pathlib.Path, default=pathlib.Path("~/zkzk-bench"))
    parser.add_argument("--timeout", type=int, default=CASE_TIMEOUT, help=f"seconds per case (default {CASE_TIMEOUT})")
    parser.add_argument("--primary-url", help="test only: an OpenAI-compatible server to use instead of Nosana")
    parser.add_argument("--primary-model", help="test only: the model on --primary-url")
    args = parser.parse_args()
    if bool(args.primary_url) != bool(args.primary_model):
        parser.error("--primary-url and --primary-model go together")

    asked = f"{args.case or ''},{args.only or ''}"
    if any(mode in asked for mode in OLD_MODES):
        parser.error("These modes measured the code at ec7a1e6. Check out that commit to rerun them.")
    if args.list:
        print("\n".join(case.id for case in CASES))
        return 0
    if args.report:
        print(write_summary(args.report.resolve()))
        return 0
    if args.all:
        if not args.out:
            parser.error("--all needs --out")
        return run_all(args)
    if not (args.case and args.sandbox):
        parser.error("use --list, --all, --report, or --case with --sandbox")
    if args.case not in CASES_BY_ID:
        parser.error(f"unknown case {args.case}; see --list")
    if os.environ.get("MODEL_TYPE", "").strip().upper() != "NOSANA":
        parser.error("run cases through --all, or set MODEL_TYPE=NOSANA")

    sandbox = args.sandbox.expanduser().resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    row = run_case(CASES_BY_ID[args.case], sandbox, args)
    print(json.dumps(row, default=str), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
