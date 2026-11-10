"""Turn the raw benchmark rows into the summary table for the README and article.

    python3 -m benchmark.report benchmark/results/<date>
    python3 -m benchmark.report benchmark/results/<date> --cost local=0 --cost nosana=1.25

Reads every runs_<backend>.jsonl in the folder (plus meta.json) and writes
summary.md next to them: one row per task per backend, a totals row per
backend, and every failed run with the checks it missed.
"""

import argparse
import json
import pathlib
import statistics
import sys

from benchmark.tasks import TASKS

NONE = "—"


# --------------------------------------------------------------------------- #
# Loading and formatting
# --------------------------------------------------------------------------- #
def load_rows(results_dir: pathlib.Path) -> list:
    rows = []
    for path in sorted(results_dir.glob("runs_*.jsonl")):
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


def _table(header: list, body: list) -> list:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in body]
    return lines


def _values(rows: list, key: str) -> list:
    return [row[key] for row in rows if isinstance(row.get(key), (int, float))]


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


def results_section(rows: list, backends: list) -> list:
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
                str(problems) if problems else NONE,
            ])
    header = [
        "Task", "Backend", "Passed", "Route match", "Median time (s)",
        "Median tool calls", "Median model calls", "Avg tokens in", "Avg tokens out",
        "Errors / timeouts",
    ]
    return ["## Results by task", ""] + _table(header, body)


def totals_section(rows: list, backends: list, costs: dict) -> list:
    body = []
    for backend in backends:
        runs = [r for r in rows if r.get("backend") == backend]
        passed = sum(bool(r.get("success")) for r in runs)
        body.append([
            backend,
            f"**{passed}/{len(runs)}** ({100 * passed / len(runs):.0f}%)",
            _fmt(sum(_values(runs, "wall_s"))),
            _fmt(sum(_values(runs, "tokens_in"))),
            _fmt(sum(_values(runs, "tokens_out"))),
            costs.get(backend, "add with --cost"),
        ])
    header = ["Backend", "Passed", "Total time (s)", "Tokens in", "Tokens out", "Cost"]
    return ["## Totals", ""] + _table(header, body)


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
        "--cost", action="append", default=[], metavar="BACKEND=AMOUNT",
        help="cost of a backend's run, e.g. nosana=1.25 (Nosana credits before minus after)",
    )
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    rows = load_rows(results_dir)
    if not rows:
        parser.error(f"no runs_*.jsonl rows found in {results_dir}")
    meta_path = results_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    costs = dict(item.split("=", 1) for item in args.cost)
    backends = sorted({row.get("backend") for row in rows})

    lines = [f"# zkzkAgent Benchmark — {results_dir.name}", ""]
    for section in (
        setup_section(meta, backends),
        results_section(rows, backends),
        totals_section(rows, backends, costs),
        failures_section(rows),
    ):
        lines += section + [""]
    lines += [
        "A run passes only when every check for its task passes. Times include",
        "network round trips for remote backends. Raw rows: `runs_<backend>.jsonl`;",
        "full agent output per run: `logs/`.",
    ]

    summary = "\n".join(lines) + "\n"
    (results_dir / "summary.md").write_text(summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
