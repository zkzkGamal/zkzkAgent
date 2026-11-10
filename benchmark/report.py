"""Turn the raw benchmark rows into the summary table for the README and article.

    python3 -m benchmark.report benchmark/results/<date>
    python3 -m benchmark.report benchmark/results/<date> --price nosana=0.20/2.00 --window nosana=131072

Reads every runs_<backend>.jsonl and speed_<backend>.jsonl in the folder
(plus meta.json) and writes summary.md next to them: one row per task per
backend, totals with time and cost per successful task, context use, speed,
and every failed run with the checks it missed.

--price is USD per 1M input/output tokens, so cost comes from the token counts.
--window is a context window the folder can't know (Ollama's comes from meta.json).
"""

import argparse
import json
import pathlib
import re
import statistics
import sys

from benchmark.tasks import TASKS

NONE = "—"


# --------------------------------------------------------------------------- #
# Loading and formatting
# --------------------------------------------------------------------------- #
def load_rows(results_dir: pathlib.Path, prefix: str = "runs") -> list:
    rows = []
    for path in sorted(results_dir.glob(f"{prefix}_*.jsonl")):
        with open(path) as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    return rows


def _median(values: list):
    return statistics.median(values) if values else None


def _mean(values: list):
    return statistics.mean(values) if values else None


def _fmt(value, digits: int = 1) -> str:
    if value is None:
        return NONE
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.{digits}f}"
    return f"{int(value):,}"


def _usd(value) -> str:
    return NONE if value is None else f"${value:.4f}"


def _table(header: list, body: list) -> list:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return lines


def _values(rows: list, key: str) -> list:
    return [row[key] for row in rows if isinstance(row.get(key), (int, float))]


# --------------------------------------------------------------------------- #
# Cost and context
# --------------------------------------------------------------------------- #
def parse_prices(items: list) -> dict:
    """["nosana=0.20/2.00"] -> {"nosana": (0.20, 2.00)} in USD per 1M tokens."""
    prices = {}
    for item in items:
        backend, _, value = item.partition("=")
        price_in, _, price_out = value.partition("/")
        prices[backend] = (float(price_in), float(price_out))
    return prices


def run_cost(row: dict, price) -> float | None:
    if price is None:
        return None
    return (row.get("tokens_in", 0) * price[0] + row.get("tokens_out", 0) * price[1]) / 1e6


def context_window(info: dict, override=None):
    """Tokens the model could see: --window, else num_ctx, else `ollama ps`."""
    if override:
        return int(override)
    if info.get("num_ctx"):
        return info["num_ctx"]
    lines = [line for line in (info.get("ollama_ps") or "").splitlines() if line.strip()]
    if len(lines) >= 2:
        header, values = re.split(r"\s{2,}", lines[0].strip()), re.split(r"\s{2,}", lines[1].strip())
        if "CONTEXT" in header and len(values) == len(header):
            return int(values[header.index("CONTEXT")])
    return None


def per_call(row: dict):
    """Average prompt size of one model call in this run."""
    calls = row.get("n_llm_calls")
    return row.get("tokens_in", 0) / calls if calls else None


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def setup_section(meta: dict, backends: list) -> list:
    lines = ["## Setup", ""]
    body = []
    for backend in backends:
        info = meta.get(backend, {})
        body.append([
            backend,
            f"`{info.get('model', NONE)}`" + (" (reasoning on)" if info.get("reasoning") else ""),
            str(info.get("reps", NONE)),
            info.get("started_at", NONE),
            f"`{str(info.get('git_commit', NONE))[:7]}`" + (" (dirty)" if info.get("git_dirty") else ""),
        ])
    lines += _table(["Backend", "Model", "Reps", "Started", "Commit"], body)

    first = meta.get(backends[0], {}) if backends else {}
    if first:
        lines += [
            "",
            f"Machine running the agent and tools: {first.get('cpu', NONE)}, "
            f"{first.get('ram', NONE)} RAM, GPU: {first.get('gpu', NONE)}, {first.get('os', NONE)}.",
        ]
    return lines


def results_section(rows: list, backends: list, prices: dict) -> list:
    body = []
    for task in TASKS:
        for backend in backends:
            runs = [r for r in rows if r.get("backend") == backend and r.get("task") == task.id]
            if not runs:
                continue
            passed = sum(bool(r.get("success")) for r in runs)
            routed = [r for r in runs if r.get("route") is not None]
            route_ok = sum(bool(r.get("route_match")) for r in routed)
            problems = sum(bool(r.get("error") or r.get("timed_out")) for r in runs)
            costs = [c for c in (run_cost(r, prices.get(backend)) for r in runs) if c is not None]
            body.append([
                f"{task.id} {task.name}",
                backend,
                f"**{passed}/{len(runs)}**",
                f"{route_ok}/{len(routed)}" if routed else NONE,
                _fmt(_median(_values(runs, "wall_s"))),
                _fmt(_median(_values(runs, "n_tool_calls"))),
                _fmt(_median(_values(runs, "n_llm_calls"))),
                _fmt(_mean(_values(runs, "tokens_in")), 0),
                _fmt(_mean(_values(runs, "tokens_out")), 0),
                _usd(_mean(costs)),
                str(problems) if problems else NONE,
            ])
    header = [
        "Task", "Backend", "Passed", "Route match", "Median time (s)",
        "Median tool calls", "Median model calls", "Avg tokens in", "Avg tokens out",
        "Avg cost", "Errors / timeouts",
    ]
    return ["## Results by task", ""] + _table(header, body)


def totals_section(rows: list, backends: list, prices: dict) -> list:
    body = []
    for backend in backends:
        runs = [r for r in rows if r.get("backend") == backend]
        passed = sum(bool(r.get("success")) for r in runs)
        wall = sum(_values(runs, "wall_s"))
        price = prices.get(backend)
        cost = sum(run_cost(r, price) for r in runs) if price else None
        body.append([
            backend,
            f"**{passed}/{len(runs)}** ({100 * passed / len(runs):.0f}%)",
            _fmt(wall),
            _fmt(wall / passed) if passed else NONE,
            _fmt(sum(_values(runs, "tokens_in"))),
            _fmt(sum(_values(runs, "tokens_out"))),
            _usd(cost) if price else "local hardware",
            (_usd(cost / passed) if passed else NONE) if price else NONE,
        ])
    header = [
        "Backend", "Passed", "Total time (s)", "Time per successful task (s)",
        "Tokens in", "Tokens out", "Cost", "Cost per successful task",
    ]
    lines = ["## Totals", ""] + _table(header, body)
    if prices:
        lines += ["", "Cost = tokens × listed price: " + ", ".join(
            f"{b} ${p[0]:.2f} in / ${p[1]:.2f} out per 1M tokens" for b, p in prices.items()
        ) + "."]
    return lines


def context_section(rows: list, backends: list, meta: dict, windows: dict) -> list:
    body = []
    for backend in backends:
        runs = [r for r in rows if r.get("backend") == backend]
        window = context_window(meta.get(backend, {}), windows.get(backend))
        averages = [(per_call(r), r.get("task")) for r in runs if per_call(r) is not None]
        largest_avg, largest_task = max(averages) if averages else (None, None)
        largest_call = max(_values(runs, "max_tokens_in"), default=0) or None  # newer rows only
        biggest = largest_call or largest_avg
        body.append([
            backend,
            _fmt(window),
            _fmt(_median([a for a, _ in averages]), 0),
            f"{_fmt(largest_avg, 0)} ({largest_task})" if largest_avg else NONE,
            _fmt(largest_call),
            f"{100 * biggest / window:.0f}%" if window and biggest else NONE,
        ])
    header = [
        "Backend", "Context window", "Median prompt per call", "Largest run average per call",
        "Largest single prompt", "Largest as % of window",
    ]
    return ["## Context use", ""] + _table(header, body) + [
        "",
        "Prompt tokens per model call: system prompt, every tool schema and the history so far.",
        "The window must also hold the reply (and any reasoning).",
    ]


def speed_section(speed_rows: list) -> list:
    if not speed_rows:
        return []
    body = []
    for backend in sorted({r.get("backend") for r in speed_rows}):
        runs = [r for r in speed_rows if r.get("backend") == backend]
        ok = [r for r in runs if not r.get("error")]
        body.append([
            backend,
            f"{len(ok)}/{len(runs)}",
            _fmt(_median(_values(ok, "tokens_in")), 0),
            _fmt(_median(_values(ok, "ttft_s")), 2),
            _fmt(_median(_values(ok, "tok_per_s"))),
            _fmt(_median(_values(ok, "server_tok_per_s"))),
            "yes" if any(r.get("reasoning_seen") for r in ok) else "no",
        ])
    header = [
        "Backend", "Calls OK", "Prompt tokens", "Median time to first token (s)",
        "Median tokens/s", "Median tokens/s (Ollama's clock)", "Reasoning tokens",
    ]
    return ["## Speed", ""] + _table(header, body) + [
        "",
        "One executor call (system prompt + all tool schemas + a short question), streamed.",
        "First token counts reasoning too. Tokens/s = output tokens over the time after the first token.",
    ]


def failures_section(rows: list) -> list:
    lines = ["## Failed runs", ""]
    failed = [r for r in rows if not r.get("success")]
    if not failed:
        return lines + ["None."]
    for r in failed:
        if r.get("error"):
            why = f"error: {r['error']}"
        else:
            missed = [name for name, ok in (r.get("checks") or {}).items() if not ok]
            why = "missed: " + ", ".join(missed)
        lines.append(f"- {r.get('backend')} {r.get('task')} rep {r.get('rep')}: {why} ({r.get('log', 'no log')})")
    return lines


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="benchmark.report", description="Summarise zkzkAgent benchmark results."
    )
    parser.add_argument("results_dir", type=pathlib.Path, help="folder with runs_<backend>.jsonl files")
    parser.add_argument(
        "--price", action="append", default=[], metavar="BACKEND=IN/OUT",
        help="USD per 1M input/output tokens, e.g. nosana=0.20/2.00",
    )
    parser.add_argument(
        "--window", action="append", default=[], metavar="BACKEND=TOKENS",
        help="context window to show for a backend, e.g. nosana=131072",
    )
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    rows = load_rows(results_dir)
    if not rows:
        parser.error(f"no runs_*.jsonl rows found in {results_dir}")
    meta_path = results_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    prices = parse_prices(args.price)
    windows = dict(item.split("=", 1) for item in args.window)
    backends = sorted({row.get("backend") for row in rows})

    lines = [f"# zkzkAgent Benchmark — {results_dir.name}", ""]
    for section in (
        setup_section(meta, backends),
        results_section(rows, backends, prices),
        totals_section(rows, backends, prices),
        context_section(rows, backends, meta, windows),
        speed_section(load_rows(results_dir, "speed")),
        failures_section(rows),
    ):
        if section:
            lines += section + [""]
    lines += [
        "A run passes only when every check for its task passes. Times include",
        "network round trips for remote backends. Raw rows: `runs_<backend>.jsonl`",
        "and `speed_<backend>.jsonl`; full agent output per run: `logs/`.",
    ]

    summary = "\n".join(lines) + "\n"
    (results_dir / "summary.md").write_text(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
