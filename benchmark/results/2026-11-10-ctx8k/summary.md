# zkzkAgent Benchmark — 2026-11-10-ctx8k

## Setup

| Backend | Model | Reps | Started | Commit |
|---|---|---|---|---|
| local-2b-8k | `qwen3.5:2b-q4_K_M` | 3 | 2026-11-10T13:54:22 | `ad09b20` (dirty) |
| local-4b-8k | `qwen3:4b` (reasoning on) | 3 | 2026-11-10T13:57:58 | `ad09b20` (dirty) |

Machine running the agent and tools: Intel(R) Core(TM) i7-10850H CPU @ 2.70GHz, 31 GB RAM, GPU: Quadro T2000 with Max-Q Design, 4096 MiB, Linux-6.8.0-138-generic-x86_64-with-glibc2.35.

## Results by task

| Task | Backend | Passed | Route match | Median time (s) | Median tool calls | Median model calls | Avg tokens in | Avg tokens out | Avg cost | Errors / timeouts |
|---|---|---|---|---|---|---|---|---|---|---|
| T4 build_app | local-2b-8k | **0/3** | 1/1 | 45.9 | 4 | 7 | 16,536 | 1,047 | — | 2 |
| T4 build_app | local-4b-8k | **0/3** | 2/2 | 599.0 | 5 | 8 | 18,906 | 11,156 | — | 1 |

## Totals

| Backend | Passed | Total time (s) | Time per successful task (s) | Tokens in | Tokens out | Cost | Cost per successful task |
|---|---|---|---|---|---|---|---|
| local-2b-8k | **0/3** (0%) | 130.3 | — | 49,609 | 3,141 | local hardware | — |
| local-4b-8k | **0/3** (0%) | 1,198.1 | — | 37,812 | 22,313 | local hardware | — |

## Context use

| Backend | Context window | Median prompt per call | Largest run average per call | Largest single prompt | Largest as % of window |
|---|---|---|---|---|---|
| local-2b-8k | 8,192 | 2,279 | 2,450 (T4) | 3,745 | 46% |
| local-4b-8k | 8,192 | 2,363 | 2,380 (T4) | 3,340 | 41% |

Prompt tokens per model call: system prompt, every tool schema and the history so far.
The window must also hold the reply (and any reasoning).

## Failed runs

- local-2b-8k T4 rep 1: error: ResponseError: XML syntax error on line 50: element <function> closed by </parameter> (status code: 500) (logs/local-2b-8k_T4_rep1.log)
- local-2b-8k T4 rep 2: missed: files_exist, calculates (logs/local-2b-8k_T4_rep2.log)
- local-2b-8k T4 rep 3: error: ResponseError: XML syntax error on line 31: element <function> closed by </parameter> (status code: 500) (logs/local-2b-8k_T4_rep3.log)
- local-4b-8k T4 rep 1: error: timed out after 900s (logs/local-4b-8k_T4_rep1.log)
- local-4b-8k T4 rep 2: missed: get_root, calculates (logs/local-4b-8k_T4_rep2.log)
- local-4b-8k T4 rep 3: missed: files_exist, get_root, calculates (logs/local-4b-8k_T4_rep3.log)

A run passes only when every check for its task passes. Times include
network round trips for remote backends. Raw rows: `runs_<backend>.jsonl`
and `speed_<backend>.jsonl`; full agent output per run: `logs/`.
